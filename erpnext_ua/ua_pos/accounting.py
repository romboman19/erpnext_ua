from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt


def profile_payment_modes(pos_profile: str) -> set[str]:
	profile = frappe.get_cached_doc("POS Profile", pos_profile)
	return {row.mode_of_payment for row in profile.payments if row.mode_of_payment}


def validate_desk_runtime(desk) -> None:
	if not desk.pos_profile:
		frappe.throw(_("Для каси {0} не вибрано POS Profile ERPNext").format(desk.name))
	if not desk.cash_account:
		frappe.throw(_("Для каси {0} не вибрано рахунок готівки").format(desk.name))
	profile = frappe.get_cached_doc("POS Profile", desk.pos_profile)
	if profile.disabled:
		frappe.throw(_("POS Profile {0} вимкнено").format(profile.name))
	if not profile.update_stock:
		frappe.throw(_("У POS Profile {0} потрібно увімкнути оновлення складу").format(profile.name))
	if profile.company != desk.company or profile.warehouse != desk.warehouse:
		frappe.throw(
			_("Компанія або склад каси {0} не відповідають POS Profile {1}").format(
				desk.name, profile.name
			)
		)


def payment_methods_for_desk(desk, configured_methods: list[dict]) -> list[dict]:
	validate_desk_runtime(desk)
	allowed = profile_payment_modes(desk.pos_profile)
	return [row for row in configured_methods if row["mode_of_payment"] in allowed]


def make_sales_invoice(order, desk):
	validate_desk_runtime(desk)
	is_return = order.order_type == "Return"
	original_invoice = (
		frappe.db.get_value("POS Order", order.return_against, "sales_invoice") if is_return else None
	)
	if is_return and not original_invoice:
		frappe.throw(_("Первинний чек не має проведеного Sales Invoice"))

	payments = [
		_payment_row(desk, row, is_return=is_return)
		for row in order.payments_plan
		if row.status == "Confirmed"
	]
	if not payments:
		frappe.throw(_("Чек не має підтвердженої оплати"))

	si = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"company": desk.company,
			"customer": order.customer,
			"is_pos": 1,
			"is_created_using_pos": 0,
			"pos_profile": desk.pos_profile,
			"update_stock": 1,
			"ignore_pricing_rule": 1,
			"is_return": 1 if is_return else 0,
			"return_against": original_invoice,
			"set_warehouse": desk.warehouse,
			"ua_pos_order": order.name,
			"ua_pos_desk": desk.name,
			"ua_pos_shift": order.operational_shift,
			"ua_pos_employee": order.employee,
			"items": [_invoice_item(row, is_return=is_return) for row in order.items],
			"payments": payments,
		}
	)
	# for_validate=True applies missing ERPNext dimensions without replacing the
	# confirmed payment rows with zero-valued defaults from the POS Profile.
	si.set_missing_values(for_validate=True)
	expected_total = -flt(order.grand_total, 2) if is_return else flt(order.grand_total, 2)
	si.calculate_taxes_and_totals()
	if abs(flt(si.grand_total, 2) - expected_total) > 0.01:
		frappe.throw(
			_("Сума Sales Invoice {0} не відповідає сумі чека {1}").format(
				frappe.format_value(si.grand_total, {"fieldtype": "Currency"}),
				frappe.format_value(expected_total, {"fieldtype": "Currency"}),
			)
		)
	si.insert(ignore_permissions=True)
	si.submit()
	return si


def apply_cash_desk_payment_accounts(doc, method=None) -> None:
	"""Restore desk-specific accounts after ERPNext applies Mode of Payment defaults."""
	if not doc.get("ua_pos_order") or not doc.get("ua_pos_desk"):
		return
	desk = frappe.get_cached_doc("POS Cash Desk", doc.ua_pos_desk)
	validate_desk_runtime(desk)
	order = frappe.get_doc("POS Order", doc.ua_pos_order)
	payment_kinds = {
		row.mode_of_payment: row.kind
		for row in order.payments_plan
		if row.status == "Confirmed"
	}
	for payment in doc.payments:
		kind = payment_kinds.get(payment.mode_of_payment)
		if not kind:
			frappe.throw(
				_("Оплата {0} відсутня у підтвердженому плані чека {1}").format(
					payment.mode_of_payment, order.name
				)
			)
		payment.account = _payment_account(desk, payment.mode_of_payment, kind)


def create_accounted_cash_movement(
	*,
	desk,
	movement_data: dict,
	debit_account: str,
	credit_account: str,
	counterparty_account: str,
):
	validate_desk_runtime(desk)
	amount = flt(movement_data.get("amount"), 2)
	if amount <= 0:
		frappe.throw(_("Сума касового руху має бути більшою за нуль"))
	_validate_ledger_account(debit_account, desk.company)
	_validate_ledger_account(credit_account, desk.company)
	if debit_account == credit_account:
		frappe.throw(_("Дебетовий і кредитовий рахунки касового руху мають відрізнятися"))

	movement = frappe.get_doc(
		{
			"doctype": "POS Cash Movement",
			**movement_data,
			"counterparty_account": counterparty_account,
		}
	).insert(ignore_permissions=True)
	journal_entry = _make_journal_entry(
		desk,
		movement,
		debit_account=debit_account,
		credit_account=credit_account,
		amount=amount,
	)
	movement.journal_entry = journal_entry.name
	movement.save(ignore_permissions=True)
	movement.submit()
	return movement


def create_manual_cash_movement(*, desk, movement_data: dict, expense_account: str | None = None):
	movement_type = movement_data["movement_type"]
	if movement_type == "Cash In":
		_require_transfer_account(desk)
		debit_account = desk.cash_account
		credit_account = desk.cash_transfer_account
		counterparty_account = desk.cash_transfer_account
	elif movement_type == "Incassation Out":
		_require_transfer_account(desk)
		debit_account = desk.cash_transfer_account
		credit_account = desk.cash_account
		counterparty_account = desk.cash_transfer_account
	elif movement_type == "Expense":
		if not expense_account:
			frappe.throw(_("Для витрати з каси виберіть рахунок витрат"))
		_validate_profit_and_loss_account(expense_account, desk.company, root_type="Expense")
		debit_account = expense_account
		credit_account = desk.cash_account
		counterparty_account = expense_account
	else:
		frappe.throw(_("Непідтримувана бухгалтерська касова операція {0}").format(movement_type))
	return create_accounted_cash_movement(
		desk=desk,
		movement_data=movement_data,
		debit_account=debit_account,
		credit_account=credit_account,
		counterparty_account=counterparty_account,
	)


def create_shift_discrepancy_movement(
	*,
	desk,
	shift,
	employee: str,
	discrepancy: float,
	comment: str,
	idem_key: str,
):
	amount = abs(flt(discrepancy, 2))
	if not amount:
		return None
	if not desk.cash_difference_account:
		frappe.throw(
			_(
				"Для каси {0} задайте рахунок нестач і надлишків перед закриттям зміни з розбіжністю"
			).format(desk.name)
		)
	_validate_profit_and_loss_account(desk.cash_difference_account, desk.company)
	is_surplus = discrepancy > 0
	return create_accounted_cash_movement(
		desk=desk,
		movement_data={
			"cash_desk": desk.name,
			"operational_shift": shift.name,
			"employee": employee,
			"direction": "In" if is_surplus else "Out",
			"movement_type": "Correction",
			"amount": amount,
			"currency": "UAH",
			"is_cash_drawer": 1,
			"basis_doctype": "POS Operational Shift",
			"basis_name": shift.name,
			"idem_key": f"shift-discrepancy:{shift.name}:{idem_key}",
			"notes": comment.strip(),
		},
		debit_account=desk.cash_account if is_surplus else desk.cash_difference_account,
		credit_account=desk.cash_difference_account if is_surplus else desk.cash_account,
		counterparty_account=desk.cash_difference_account,
	)


def _invoice_item(row, *, is_return: bool) -> dict:
	gross = flt(row.qty) * flt(row.rate)
	discount_percentage = flt(row.discount_amount) * 100 / gross if gross else 0
	net_rate = (gross - flt(row.discount_amount)) / flt(row.qty) if flt(row.qty) else 0
	return {
		"item_code": row.item_code,
		"qty": -row.qty if is_return else row.qty,
		"uom": row.uom,
		"price_list_rate": row.rate,
		"rate": net_rate,
		"discount_percentage": discount_percentage,
		"warehouse": row.warehouse,
		"batch_no": row.batch_no,
		"serial_no": row.serial_no,
	}


def _payment_row(desk, payment, *, is_return: bool) -> dict:
	if payment.mode_of_payment not in profile_payment_modes(desk.pos_profile):
		frappe.throw(
			_("Спосіб оплати {0} не дозволений у POS Profile {1}").format(
				payment.mode_of_payment, desk.pos_profile
			)
		)
	mode_type = frappe.get_cached_value("Mode of Payment", payment.mode_of_payment, "type")
	if not mode_type:
		frappe.throw(_("Спосіб оплати {0} вимкнено або не знайдено").format(payment.mode_of_payment))
	account = _payment_account(desk, payment.mode_of_payment, payment.kind)
	return {
		"mode_of_payment": payment.mode_of_payment,
		"type": mode_type,
		"account": account,
		"amount": -payment.amount if is_return else payment.amount,
	}


def _payment_account(desk, mode_of_payment: str, kind: str) -> str:
	account = (
		desk.cash_account
		if kind == "Cash"
		else frappe.db.get_value(
			"Mode of Payment Account",
			{"parent": mode_of_payment, "company": desk.company},
			"default_account",
		)
	)
	if not account:
		frappe.throw(
			_("Для способу оплати {0} не задано рахунок компанії {1}").format(
				mode_of_payment, desk.company
			)
		)
	_validate_ledger_account(account, desk.company)
	return account


def _make_journal_entry(desk, movement, *, debit_account: str, credit_account: str, amount: float):
	profile = frappe.get_cached_doc("POS Profile", desk.pos_profile)
	cost_center = profile.cost_center or frappe.get_cached_value("Company", desk.company, "cost_center")
	accounts = [
		_journal_account_row(
			debit_account,
			debit=amount,
			credit=0,
			cost_center=cost_center,
		),
		_journal_account_row(
			credit_account,
			debit=0,
			credit=amount,
			cost_center=cost_center,
		),
	]
	entry = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": "Cash Entry",
			"company": desk.company,
			"posting_date": frappe.utils.today(),
			"user_remark": _("UA POS {0}: {1}").format(movement.name, movement.movement_type),
			"accounts": accounts,
		}
	).insert(ignore_permissions=True)
	entry.submit()
	return entry


def _journal_account_row(account: str, *, debit: float, credit: float, cost_center: str | None):
	root_type = frappe.get_cached_value("Account", account, "root_type")
	row = {
		"account": account,
		"debit_in_account_currency": debit,
		"credit_in_account_currency": credit,
	}
	if root_type in {"Expense", "Income"}:
		if not cost_center:
			frappe.throw(_("Для проводки по рахунку {0} не задано центр витрат").format(account))
		row["cost_center"] = cost_center
	return row


def _validate_ledger_account(account: str, company: str) -> None:
	details = frappe.db.get_value(
		"Account",
		account,
		["company", "account_currency", "is_group", "disabled"],
		as_dict=True,
	)
	if not details or details.company != company or details.is_group or details.disabled:
		frappe.throw(_("Рахунок {0} не є активним рахунком компанії {1}").format(account, company))
	company_currency = frappe.get_cached_value("Company", company, "default_currency")
	if details.account_currency != company_currency:
		frappe.throw(
			_("Рахунок {0} має бути у валюті компанії {1}").format(account, company_currency)
		)


def _validate_profit_and_loss_account(
	account: str,
	company: str,
	*,
	root_type: str | None = None,
) -> None:
	_validate_ledger_account(account, company)
	actual_root_type = frappe.get_cached_value("Account", account, "root_type")
	allowed = {root_type} if root_type else {"Expense", "Income"}
	if actual_root_type not in allowed:
		frappe.throw(
			_("Рахунок {0} має належати до {1}").format(account, " / ".join(sorted(allowed)))
		)


def _require_transfer_account(desk) -> None:
	if not desk.cash_transfer_account:
		frappe.throw(_("Для каси {0} не задано транзитний рахунок інкасації").format(desk.name))

"""Інтеграція Sales Invoice (POS) → фіскальний чек ПРРО.

При проведенні POS-рахунку створюється й фіскалізується PRRO Receipt через
оркестрацію. Каса визначається за POS Profile рахунку, ключ — за касиром
(власником рахунку) або ключем каси за замовчуванням.
"""

import frappe

from erpnext_ua.ua_fiscal import orchestration as orch
from erpnext_ua.ua_fiscal.fiscal_client import FiscalServerError

# Мапінг типу форми оплати ERPNext → код форми оплати ДПС
PAYFORM_CASH = 0
PAYFORM_CASHLESS = 1


def _register_for_invoice(si) -> str | None:
	if not si.get("pos_profile"):
		return None
	return frappe.db.get_value(
		"PRRO Cash Register", {"pos_profile": si.pos_profile, "status": "Active"}
	)


def _kep_key_for_invoice(si, register_name: str) -> str | None:
	"""Ключ касира (власника рахунку), інакше — ключ каси за замовчуванням."""
	key = frappe.db.get_value("UA KEP Key", {"user": si.owner, "status": "Active"})
	return key or frappe.db.get_value("PRRO Cash Register", register_name, "default_kep_key")


def _invoice_lines(si) -> list[dict]:
	lines = []
	for it in si.get("items") or []:
		lines.append({
			"code": it.item_code or it.item_name,
			"name": it.item_name or it.item_code,
			"uom": it.uom or it.stock_uom or "шт",
			"qty": abs(frappe.utils.flt(it.qty)),
			"price": frappe.utils.flt(it.rate),
			"amount": abs(frappe.utils.flt(it.amount)),
		})
	return lines


def _invoice_payments(si) -> list[dict]:
	payments = []
	for p in si.get("payments", []):
		amount = abs(frappe.utils.flt(p.amount))
		if not amount:
			continue
		code = PAYFORM_CASH if (p.type or "").lower() == "cash" else PAYFORM_CASHLESS
		row = {"code": code, "name": (p.mode_of_payment or "").upper() or "ГОТІВКА", "sum": amount}
		# решта для готівки
		if code == PAYFORM_CASH and frappe.utils.flt(si.get("change_amount")) > 0:
			row["provided"] = amount + frappe.utils.flt(si.change_amount)
			row["remains"] = frappe.utils.flt(si.change_amount)
		payments.append(row)
	if not payments:  # рахунок без POS-оплат — вважаємо готівкою на всю суму
		payments.append({"code": PAYFORM_CASH, "name": "ГОТІВКА",
						 "sum": frappe.utils.flt(si.rounded_total or si.grand_total)})
	return payments


def _related_receipt(si) -> str | None:
	if not si.get("return_against"):
		return None
	return frappe.db.get_value(
		"PRRO Receipt",
		{"sales_invoice": si.return_against, "status": "Fiscalized"},
		"name",
	)


@frappe.whitelist()
def fiscalize_invoice(sales_invoice: str, client=None) -> str | None:
	"""Створює й фіскалізує чек ПРРО з POS-рахунку. Ідемпотентно."""
	existing = frappe.db.get_value(
		"PRRO Receipt",
		{"sales_invoice": sales_invoice, "status": ("in", ("Fiscalized", "Offline"))},
		"name",
	)
	if existing:
		return existing

	si = frappe.get_doc("Sales Invoice", sales_invoice)
	register = _register_for_invoice(si)
	if not register:
		frappe.throw(
			f"Для рахунку {sales_invoice} не знайдено активної каси ПРРО "
			f"(POS Profile: {si.get('pos_profile') or '—'})",
			FiscalServerError,
		)
	kep_key = _kep_key_for_invoice(si, register)
	if not kep_key:
		frappe.throw(f"Не знайдено активного ключа КЕП для касира {si.owner}", FiscalServerError)

	total = frappe.utils.flt(si.rounded_total or si.grand_total)
	return orch.fiscalize_sale(
		cash_register=register,
		kep_key=kep_key,
		items=_invoice_lines(si),
		payments=_invoice_payments(si),
		total=total,
		receipt_type="Повернення" if si.is_return else "Продаж",
		sales_invoice=sales_invoice,
		related_receipt=_related_receipt(si),
		client=client,
	)


def on_submit(doc, method=None):
	"""Хук проведення Sales Invoice: авто-фіскалізація POS-рахунків.

	Спрацьовує лише для is_pos при увімкненій фіскалізації та наявній касі.
	Помилка не блокує проведення — чек лишається в статусі Error для повтору.
	"""
	if not doc.get("is_pos"):
		return
	settings = frappe.get_cached_doc("PRRO Settings")
	if not settings.enabled:
		return
	if not _register_for_invoice(doc):
		return
	try:
		fiscalize_invoice(doc.name)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"PRRO auto-fiscalize {doc.name}")

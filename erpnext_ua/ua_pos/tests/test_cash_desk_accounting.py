"""Transactional integration tests for the UA POS → ERPNext accounting bridge."""

from __future__ import annotations

import unittest

try:
	import frappe
except ModuleNotFoundError:  # Lightweight source-tree test environment.
	frappe = None


@unittest.skipUnless(frappe, "requires a configured Frappe site")
class TestCashDeskAccounting(unittest.TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("ua_pos_accounting_bridge")
		self.company = "POS Test Ukraine"
		self.warehouse = "Stores - PTU"
		self.cash_mode = "Готівка" if frappe.db.exists("Mode of Payment", "Готівка") else "Cash"
		self.transfer_account = "Cash - PTU"
		self.expense_account = "Administrative Expenses - PTU"
		self.cost_center = frappe.get_cached_value("Company", self.company, "cost_center")
		self.customer = frappe.db.get_value("POS Cash Desk", "POS Test Desk", "default_customer")
		self.employee = self._employee()
		self.item_code = self._service_item()
		self.cash_account = self._cash_account()
		self._set_mode_of_payment_account()
		self.profile = self._pos_profile()
		self.desk = self._cash_desk()
		self.shift = self._shift()

	def tearDown(self):
		frappe.db.rollback(save_point="ua_pos_accounting_bridge")
		frappe.clear_cache()

	def test_sale_uses_desk_cash_account_without_native_opening_entry(self):
		from erpnext_ua.ua_pos.accounting import make_sales_invoice

		order = frappe.get_doc(
			{
				"doctype": "POS Order",
				"cash_desk": self.desk.name,
				"operational_shift": self.shift.name,
				"employee": self.employee,
				"customer": self.customer,
				"status": "Paid",
				"items": [
					{
						"item_code": self.item_code,
						"item_name": self.item_code,
						"qty": 1,
						"uom": frappe.get_cached_value("Item", self.item_code, "stock_uom"),
						"rate": 100,
						"discount_amount": 20,
						"warehouse": self.warehouse,
					}
				],
				"payments_plan": [
					{
						"mode_of_payment": self.cash_mode,
						"kind": "Cash",
						"prro_payment_form": "ГОТІВКА",
						"prro_payment_means": "ГОТІВКА",
						"prro_payment_code": 0,
						"payment_context": "Звичайна оплата",
						"amount": 80,
						"currency": "UAH",
						"status": "Confirmed",
					}
				],
			}
		).insert(ignore_permissions=True)

		invoice = make_sales_invoice(order, self.desk)

		self.assertEqual(invoice.docstatus, 1)
		self.assertEqual(invoice.pos_profile, self.profile.name)
		self.assertEqual(invoice.is_created_using_pos, 0)
		self.assertEqual(invoice.ua_pos_employee, self.employee)
		self.assertAlmostEqual(float(invoice.grand_total), 80)
		self.assertAlmostEqual(float(invoice.items[0].discount_percentage), 20)
		self.assertEqual(invoice.payments[0].account, self.cash_account)
		self.assertAlmostEqual(float(invoice.payments[0].amount), 80)
		self.assertFalse(
			frappe.db.exists(
				"POS Opening Entry",
				{"pos_profile": self.profile.name, "status": "Open"},
			)
		)
		self.assertAlmostEqual(
			sum(
				float(row.debit)
				for row in frappe.get_all(
					"GL Entry",
					filters={
						"voucher_type": "Sales Invoice",
						"voucher_no": invoice.name,
						"account": self.cash_account,
						"is_cancelled": 0,
					},
					fields=["debit"],
				)
			),
			80,
		)

	def test_manual_cash_movements_submit_balanced_journal_entries(self):
		from erpnext_ua.ua_pos.accounting import create_manual_cash_movement

		cash_in_data = self._movement_data("Cash In", "In", 50, "cash-in")
		cash_in_data["denomination_counts"] = [
			{
				"context": "Transfer",
				"currency": "UAH",
				"denomination": 20,
				"qty": 2,
			},
			{
				"context": "Transfer",
				"currency": "UAH",
				"denomination": 10,
				"qty": 1,
			},
		]
		cash_in = create_manual_cash_movement(
			desk=self.desk,
			movement_data=cash_in_data,
		)
		expense = create_manual_cash_movement(
			desk=self.desk,
			movement_data=self._movement_data("Expense", "Out", 10, "expense"),
			expense_account=self.expense_account,
		)

		self.assertEqual(cash_in.docstatus, 1)
		self.assertEqual(expense.docstatus, 1)
		self.assertEqual(
			[
				(float(row.denomination), row.qty, float(row.subtotal))
				for row in cash_in.denomination_counts
			],
			[(20, 2, 40), (10, 1, 10)],
		)
		self.assertEqual(cash_in.counterparty_account, self.transfer_account)
		self.assertEqual(expense.counterparty_account, self.expense_account)
		self._assert_journal_accounts(
			cash_in.journal_entry,
			{
				self.cash_account: (50, 0),
				self.transfer_account: (0, 50),
			},
		)
		self._assert_journal_accounts(
			expense.journal_entry,
			{
				self.expense_account: (10, 0),
				self.cash_account: (0, 10),
			},
		)

	def _employee(self) -> str:
		employee = frappe.db.get_value("Employee", {"company": self.company, "status": "Active"}, "name")
		if employee:
			return employee
		return frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": "POS Bridge",
				"company": self.company,
				"gender": "Male",
				"date_of_birth": "1990-01-01",
				"date_of_joining": frappe.utils.today(),
				"status": "Active",
			}
		).insert(ignore_permissions=True).name

	def _service_item(self) -> str:
		source_item = frappe.get_doc("Item", "POS-TEST-001")
		return frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": "_Test POS Bridge Service",
				"item_name": "_Test POS Bridge Service",
				"item_group": source_item.item_group,
				"stock_uom": source_item.stock_uom,
				"is_stock_item": 0,
				"is_sales_item": 1,
			}
		).insert(ignore_permissions=True).name

	def _cash_account(self) -> str:
		parent_account = frappe.get_cached_value("Account", self.transfer_account, "parent_account")
		return frappe.get_doc(
			{
				"doctype": "Account",
				"account_name": "_Test POS Bridge Cash",
				"parent_account": parent_account,
				"company": self.company,
				"account_type": "Cash",
				"account_currency": "UAH",
			}
		).insert(ignore_permissions=True).name

	def _set_mode_of_payment_account(self):
		mode = frappe.get_doc("Mode of Payment", self.cash_mode)
		if not any(row.company == self.company for row in mode.accounts):
			mode.append(
				"accounts",
				{
					"company": self.company,
					"default_account": self.transfer_account,
				},
			)
			mode.save(ignore_permissions=True)

	def _pos_profile(self):
		return frappe.get_doc(
			{
				"doctype": "POS Profile",
				"name": "_Test POS Bridge Profile",
				"company": self.company,
				"customer": self.customer,
				"warehouse": self.warehouse,
				"currency": "UAH",
				"selling_price_list": frappe.get_single_value(
					"Selling Settings", "selling_price_list"
				),
				"write_off_account": frappe.get_cached_value(
					"Company", self.company, "write_off_account"
				),
				"write_off_cost_center": self.cost_center,
				"cost_center": self.cost_center,
				"update_stock": 1,
				"payments": [
					{
						"mode_of_payment": self.cash_mode,
						"default": 1,
					}
				],
			}
		).insert(ignore_permissions=True)

	def _cash_desk(self):
		desk = frappe.get_doc("POS Cash Desk", "POS Test Desk")
		desk.pos_profile = self.profile.name
		desk.cash_account = self.cash_account
		desk.cash_transfer_account = self.transfer_account
		desk.cash_difference_account = self.expense_account
		desk.save(ignore_permissions=True)
		return desk

	def _shift(self):
		return frappe.get_doc(
			{
				"doctype": "POS Operational Shift",
				"cash_desk": self.desk.name,
				"responsible_employee": self.employee,
				"status": "Open",
				"opened_by": "Administrator",
				"opened_at": frappe.utils.now_datetime(),
				"idem_key": "_test-pos-accounting-shift",
			}
		).insert(ignore_permissions=True)

	def _movement_data(self, movement_type: str, direction: str, amount: float, suffix: str):
		return {
			"cash_desk": self.desk.name,
			"operational_shift": self.shift.name,
			"employee": self.employee,
			"direction": direction,
			"movement_type": movement_type,
			"amount": amount,
			"currency": "UAH",
			"is_cash_drawer": 1,
			"idem_key": f"_test-pos-accounting-{suffix}",
			"notes": "Transactional integration test",
		}

	def _assert_journal_accounts(self, journal_entry: str, expected: dict):
		rows = frappe.get_all(
			"Journal Entry Account",
			filters={"parent": journal_entry},
			fields=["account", "debit_in_account_currency", "credit_in_account_currency"],
		)
		actual = {
			row.account: (
				float(row.debit_in_account_currency),
				float(row.credit_in_account_currency),
			)
			for row in rows
		}
		self.assertEqual(actual, expected)


if __name__ == "__main__":
	unittest.main()

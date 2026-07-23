from __future__ import annotations

import json
import unittest
from pathlib import Path


APP = Path(__file__).resolve().parents[1]


class TestPOSCashDeskBridgeContracts(unittest.TestCase):
	def test_cash_desk_bridges_native_profile_and_separate_cash_accounts(self):
		doctype = json.loads(
			(
				APP
				/ "ua_pos"
				/ "doctype"
				/ "pos_cash_desk"
				/ "pos_cash_desk.json"
			).read_text(encoding="utf-8")
		)
		fields = {row["fieldname"]: row for row in doctype["fields"]}

		self.assertEqual(fields["pos_profile"]["options"], "POS Profile")
		self.assertTrue(fields["pos_profile"]["reqd"])
		self.assertEqual(fields["company"]["fetch_from"], "pos_profile.company")
		self.assertEqual(fields["warehouse"]["fetch_from"], "pos_profile.warehouse")
		self.assertTrue(fields["cash_account"]["reqd"])
		self.assertTrue(fields["cash_transfer_account"]["reqd"])
		self.assertIn("cash_difference_account", fields)

	def test_upgrade_backfills_profile_accounts_and_employee_access(self):
		install = (APP / "install.py").read_text(encoding="utf-8")
		setup = (APP / "ua_pos" / "setup.py").read_text(encoding="utf-8")

		self.assertIn("backfill_cash_desk_bridge()", install)
		self.assertIn('"POS Profile"', setup)
		self.assertIn('"Employee Cash Desk Access"', setup)
		self.assertIn('"access_role": "Cashier"', setup)
		self.assertIn('"account_type": "Cash"', setup)
		self.assertIn('"інкасац"', setup)

	def test_sales_invoice_keeps_confirmed_payments_and_custom_shift_ownership(self):
		accounting = (APP / "ua_pos" / "accounting.py").read_text(encoding="utf-8")
		hooks = (APP / "hooks.py").read_text(encoding="utf-8")

		self.assertIn('"pos_profile": desk.pos_profile', accounting)
		self.assertIn('"is_created_using_pos": 0', accounting)
		self.assertIn("si.set_missing_values(for_validate=True)", accounting)
		self.assertNotIn("si.set_missing_values()", accounting)
		self.assertIn('"account": account', accounting)
		self.assertIn('"ua_pos_employee": order.employee', accounting)
		self.assertIn('"discount_percentage": discount_percentage', accounting)
		self.assertIn("apply_cash_desk_payment_accounts", hooks)

	def test_non_sale_cash_movements_require_a_submitted_journal_entry(self):
		movement = json.loads(
			(
				APP
				/ "ua_pos"
				/ "doctype"
				/ "pos_cash_movement"
				/ "pos_cash_movement.json"
			).read_text(encoding="utf-8")
		)
		fields = {row["fieldname"]: row for row in movement["fields"]}
		controller = (
			APP
			/ "ua_pos"
			/ "doctype"
			/ "pos_cash_movement"
			/ "pos_cash_movement.py"
		).read_text(encoding="utf-8")
		accounting = (APP / "ua_pos" / "accounting.py").read_text(encoding="utf-8")

		self.assertEqual(fields["journal_entry"]["options"], "Journal Entry")
		self.assertEqual(fields["counterparty_account"]["options"], "Account")
		self.assertIn("ACCOUNTED_MOVEMENT_TYPES", controller)
		self.assertIn('"voucher_type": "Cash Entry"', accounting)
		self.assertIn("entry.submit()", accounting)

	def test_expense_dialog_requires_an_expense_account(self):
		source = (
			APP / "ua_pos" / "page" / "ua_pos" / "ua_pos.js"
		).read_text(encoding="utf-8")

		self.assertIn('fieldname: "expense_account"', source)
		self.assertIn('root_type: "Expense"', source)
		self.assertIn("expense_account: values.expense_account || null", source)

	def test_visual_stock_browser_and_f6_payment_are_wired(self):
		source = (
			APP / "ua_pos" / "page" / "ua_pos" / "ua_pos.js"
		).read_text(encoding="utf-8")
		api = (APP / "ua_pos" / "api.py").read_text(encoding="utf-8")

		self.assertIn('api("stock_categories"', source)
		self.assertIn('api("stock_catalog"', source)
		self.assertIn("ua-pos-category-tree", source)
		self.assertIn("ua-pos-product-detail", source)
		self.assertIn("F6: () =>", source)
		self.assertIn('paymentDialog("cash")', source)
		self.assertNotIn("F6: discountDialog", source)
		self.assertIn("def stock_categories(", api)
		self.assertIn("def stock_catalog(", api)
		self.assertIn("i.description", api)
		self.assertIn("i.item_group", api)

	def test_cash_desk_print_controls_and_denomination_table_are_persistent(self):
		desk = json.loads(
			(
				APP
				/ "ua_pos"
				/ "doctype"
				/ "pos_cash_desk"
				/ "pos_cash_desk.json"
			).read_text(encoding="utf-8")
		)
		movement = json.loads(
			(
				APP
				/ "ua_pos"
				/ "doctype"
				/ "pos_cash_movement"
				/ "pos_cash_movement.json"
			).read_text(encoding="utf-8")
		)
		desk_fields = {row["fieldname"]: row for row in desk["fields"]}
		movement_fields = {row["fieldname"]: row for row in movement["fields"]}

		self.assertIn("require_receipt_print", desk_fields)
		self.assertIn("print_cash_documents", desk_fields)
		self.assertEqual(movement_fields["denomination_counts"]["options"], "POS Denomination Count")


if __name__ == "__main__":
	unittest.main()

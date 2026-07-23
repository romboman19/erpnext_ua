from __future__ import annotations

import unittest
from pathlib import Path

import erpnext_ua.hooks as hooks


APP = Path(__file__).resolve().parents[1]


class TestPaymentEntryNavigationContracts(unittest.TestCase):
	def test_purchase_invoice_list_script_is_registered(self):
		self.assertEqual(
			hooks.doctype_list_js["Purchase Invoice"],
			"public/js/purchase_invoice_payment_list.js",
		)

	def test_single_and_batch_navigation_contracts_are_present(self):
		javascript = (APP / "public" / "js" / "purchase_invoice_payment_list.js").read_text(
			encoding="utf-8"
		)
		self.assertIn('result.mode === "single"', javascript)
		self.assertIn('frappe.set_route("Form", "Payment Entry", payment.name)', javascript)
		self.assertIn("frappe.realtime.on(COMPLETION_EVENT", javascript)
		self.assertIn("state.in_flight.has(key)", javascript)
		self.assertIn("payment_link(row.name)", javascript)
		self.assertLess(
			javascript.index("state.in_flight.add(key)"),
			javascript.index("const confirmed = await"),
		)

	def test_backend_reuses_drafts_and_never_submits_them(self):
		service = (APP / "ua_payments" / "service.py").read_text(encoding="utf-8")
		self.assertIn('filters={"name": ("in",', service)
		self.assertIn('"docstatus": 0', service)
		self.assertIn("payment.insert(ignore_mandatory=True)", service)
		self.assertIn("deduplicate=True", service)
		self.assertIn("frappe.publish_realtime(", service)
		self.assertNotIn("payment.submit()", service)


if __name__ == "__main__":
	unittest.main()

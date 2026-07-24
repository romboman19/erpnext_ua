"""Read-only integration tests for the UA POS visual stock browser."""

from __future__ import annotations

import json
import unittest

try:
	import frappe
except ModuleNotFoundError:  # Lightweight source-tree test environment.
	frappe = None


@unittest.skipUnless(frappe, "requires a configured Frappe site")
class TestStockCatalog(unittest.TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		desks = frappe.get_all(
			"POS Cash Desk",
			filters={
				"status": "Active",
				"warehouse": ("is", "set"),
			},
			pluck="name",
			limit=1,
		)
		employees = frappe.get_all("Employee", pluck="name", limit=1)
		if not desks or not employees:
			self.skipTest("test site has no configured active POS cash desk or employee")
		self.desk = desks[0]
		self.employee = employees[0]
		self.token = "_test-stock-catalog"
		from erpnext_ua.ua_pos.services.common import SESSION_TTL, session_key

		frappe.cache.set_value(
			session_key(self.token),
			json.dumps(
				{
					"employee": self.employee,
					"cash_desk": self.desk,
					"access_role": "Manager",
				}
			),
			expires_in_sec=SESSION_TTL,
		)

	def tearDown(self):
		from erpnext_ua.ua_pos.services.common import session_key

		frappe.cache.delete_value(session_key(self.token))

	def test_catalog_returns_tree_and_paginated_product_cards(self):
		from erpnext_ua.ua_pos.api import stock_catalog, stock_categories, stock_warehouses

		categories = stock_categories(self.token)
		warehouses = stock_warehouses(self.token)
		result = stock_catalog(self.token, limit=2)

		self.assertTrue(categories)
		self.assertTrue(warehouses)
		self.assertIn("items", result)
		self.assertIn("has_more", result)
		self.assertLessEqual(len(result["items"]), 2)
		if result["items"]:
			item = result["items"][0]
			self.assertIn("item_group", item)
			self.assertIn("description", item)
			self.assertIn("actual_qty", item)
			self.assertIn("rate", item)

	def test_catalog_accepts_warehouse_and_availability_filters(self):
		from erpnext_ua.ua_pos.api import stock_catalog, stock_warehouses

		warehouse = stock_warehouses(self.token)[0]["name"]
		result = stock_catalog(self.token, warehouse=warehouse, availability="in_stock", limit=2)

		self.assertIn("items", result)
		self.assertTrue(all(float(row["actual_qty"] or 0) > 0 for row in result["items"]))


if __name__ == "__main__":
	unittest.main()

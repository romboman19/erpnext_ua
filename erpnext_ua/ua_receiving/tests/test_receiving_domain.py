import unittest

from erpnext_ua.ua_receiving.domain import resolve_receipt_warehouse, suggest_selling_price


class TestReceivingDomain(unittest.TestCase):
	def test_receipt_warehouse_prefers_document_data(self):
		self.assertEqual(resolve_receipt_warehouse("Row Store", "Header Store", "Manual"), "Row Store")
		self.assertEqual(resolve_receipt_warehouse(None, "Header Store", "Manual"), "Header Store")
		self.assertEqual(resolve_receipt_warehouse(None, None, "Manual"), "Manual")

	def test_suggested_price_rounds_up_without_losing_margin(self):
		self.assertEqual(suggest_selling_price(100, 30, 1), 130.0)
		self.assertEqual(suggest_selling_price(101.10, 30, 1), 132.0)
		self.assertEqual(suggest_selling_price(101.10, 30, 5), 135.0)

	def test_missing_or_invalid_cost_has_no_suggestion(self):
		self.assertIsNone(suggest_selling_price(None, 30, 1))
		self.assertIsNone(suggest_selling_price(0, 30, 1))


if __name__ == "__main__":
	unittest.main()

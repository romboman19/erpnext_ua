import unittest
import xml.etree.ElementTree as ET

from erpnext_ua.ua_fiscal import xml_builder as xb


class TestFiscalTotals(unittest.TestCase):
	@staticmethod
	def _head():
		return xb.build_check_head(
			doctype=xb.DOCTYPE_SALE,
			subtype=xb.SUBTYPE_GOODS,
			fop={
				"tax_id": "3184710691",
				"fop_full_name": "Тест Тестович",
				"prro_registered_name": "ТЕСТ ТЕСТОВИЧ",
			},
			register={
				"unit_name": "Магазин",
				"unit_address": "м. Рівне",
				"fiscal_number": "4000099999",
				"local_number": 1,
			},
			local_number=1,
			cashier_name="Касир Тестовий",
			testing=True,
		)

	def test_registered_name_is_copied_to_orgnm_verbatim(self):
		head = self._head()
		self.assertEqual(head["ORGNM"], "ТЕСТ ТЕСТОВИЧ")

	def test_excluded_tax_is_added_to_line_total(self):
		xml = xb.build_sale_check(
			self._head(),
			items=[{
				"code": "SKU", "name": "Товар", "uom": "шт", "qty": 1,
				"price": 100, "amount": 100, "letters": "А",
			}],
			payments=[{"code": 0, "name": "ГОТІВКА", "sum": 120}],
			total=120,
			taxes=[{
				"type": 0, "name": "ПДВ", "letter": "А", "prc": 20,
				"sign": True, "turnover": 100, "sum": 20,
			}],
		)
		xb.validate_document(xml)
		root = ET.fromstring(xml)
		self.assertEqual(root.findtext("CHECKTAX/ROW/SIGN"), "true")
		self.assertEqual(root.findtext("CHECKTOTAL/SUM"), "120.00")

	def test_official_rounding_fields(self):
		xml = xb.build_sale_check(
			self._head(),
			items=[{
				"code": "SKU", "name": "Товар", "uom": "шт", "qty": 1,
				"price": 12.57, "amount": 12.57, "letters": "А",
			}],
			payments=[{"code": 0, "name": "ГОТІВКА", "sum": 12.60}],
			total=12.60,
			no_rounding_total=12.57,
			rounding_sum=-0.03,
			taxes=[{
				"type": 0, "name": "ПДВ", "letter": "А", "prc": 20,
				"sign": False, "turnover": 12.57, "sum": 2.09,
			}],
		)
		xb.validate_document(xml)
		root = ET.fromstring(xml)
		self.assertEqual(root.findtext("CHECKTOTAL/RNDSUM"), "-0.03")
		self.assertEqual(root.findtext("CHECKTOTAL/NORNDSUM"), "12.57")


if __name__ == "__main__":
	unittest.main()

"""Наскрізний тест оркестрації зміни ПРРО з мок-клієнтом.

Мережа не викликається: FakeClient валідує кожен документ проти вбудованих XSD
і повертає квитанцію з фіскальним номером. Запуск:

    bench --site <site> execute erpnext_ua.ua_fiscal.tests.test_prro_flow.run
"""

import frappe

from erpnext_ua.ua_fiscal import orchestration as orch
from erpnext_ua.ua_fiscal import xml_builder as xb

TESTNAME = "_prro_selftest"


def _cleanup(company):
	for dt in ["PRRO Receipt", "PRRO Shift"]:
		for n in frappe.get_all(dt, filters={"cash_register": TESTNAME}, pluck="name"):
			frappe.delete_doc(dt, n, force=True)
	if frappe.db.exists("PRRO Cash Register", TESTNAME):
		frappe.delete_doc("PRRO Cash Register", TESTNAME, force=True)
	for n in frappe.get_all("UA KEP Key", filters={"user": "Administrator"}, pluck="name"):
		frappe.delete_doc("UA KEP Key", n, force=True)
	if frappe.db.exists("FOP Profile", company):
		frappe.delete_doc("FOP Profile", company, force=True)
	frappe.db.commit()


class FakeFiscalClient:
	"""Замість мережі: XSD-валідація документа + видача фіскального номера."""

	def __init__(self):
		self.settings = frappe.get_single("PRRO Settings")
		self.settings.mode = "Тестовий"
		self.counter = 5000000000
		self.sent = []

	def sign(self, xml: bytes, kep_key: str) -> bytes:
		xb.validate_document(xml)  # кине ValueError, якщо XML невалідний
		from lxml import etree

		self.sent.append(etree.fromstring(xml).tag)
		return b"SIGNED:" + xml

	def send_document(self, signed: bytes) -> bytes:
		self.counter += 1
		return (
			'<?xml version="1.0" encoding="windows-1251"?>'
			'<TICKET xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
			f"<UID>x</UID><ORDERTAXNUM>{self.counter}</ORDERTAXNUM>"
			"<OFFLINESESSIONID>82563</OFFLINESESSIONID>"
			"<OFFLINESEED>179625192271939</OFFLINESEED>"
			"<ERRORCODE>0</ERRORCODE><VER>1</VER></TICKET>"
		).encode("windows-1251")


def run():
	frappe.set_user("Administrator")
	company = frappe.get_all("Company", pluck="name")[0]
	_cleanup(company)

	frappe.get_single("PRRO Settings").db_set("mode", "Тестовий")
	fop = frappe.get_doc({
		"doctype": "FOP Profile", "company": company, "fop_full_name": "Тест Тестович",
		"tax_id": "3184710691", "single_tax_group": "2", "tax_rate_mode": "Фіксована ставка",
	}).insert(ignore_permissions=True)
	kf = frappe.get_doc({"doctype": "File", "file_name": "dummy.key", "is_private": 1,
						 "content": "dummy"}).insert(ignore_permissions=True)
	kep = frappe.get_doc({
		"doctype": "UA KEP Key", "user": "Administrator", "subject_name": "Касир Тестовий",
		"tax_id": "3184710691", "status": "Active", "key_file": kf.file_url, "key_password": "x",
	}).insert(ignore_permissions=True)
	frappe.get_doc({
		"doctype": "PRRO Cash Register", "register_name": TESTNAME, "fop_profile": fop.name,
		"fiscal_number": "4000099999", "unit_name": "Інтернет-магазин HUNTER",
		"unit_address": "м. Рівне, вул. Тестова, 1", "default_kep_key": kep.name,
	}).insert(ignore_permissions=True)
	frappe.db.commit()

	client = FakeFiscalClient()

	shift_name = orch.open_shift(TESTNAME, kep.name, client=client)
	assert frappe.db.get_value("PRRO Shift", shift_name, "status") == "Open"

	r1 = orch.fiscalize_sale(
		TESTNAME, kep.name,
		items=[{"code": "SKU1", "name": "Ніж «Ведмідь»", "uom": "шт", "qty": 2,
				"price": 450.0, "amount": 900.0}],
		payments=[{"code": 0, "name": "ГОТІВКА", "sum": 900.0, "provided": 1000.0, "remains": 100.0}],
		total=900.0, client=client)
	assert frappe.db.get_value("PRRO Receipt", r1, "status") == "Fiscalized"

	r2 = orch.fiscalize_sale(
		TESTNAME, kep.name,
		items=[{"code": "SKU1", "name": "Ніж «Ведмідь»", "uom": "шт", "qty": 1,
				"price": 450.0, "amount": 450.0}],
		payments=[{"code": 0, "name": "ГОТІВКА", "sum": 450.0}],
		total=450.0, receipt_type="Повернення", related_receipt=r1, client=client)

	orch.close_shift(TESTNAME, kep.name, client=client)
	shift = frappe.get_doc("PRRO Shift", shift_name)
	assert shift.status == "Closed"
	assert not frappe.db.get_value("PRRO Cash Register", TESTNAME, "current_shift")
	assert shift.sales_total == 900.0 and shift.refunds_total == 450.0

	nums = sorted(frappe.db.get_value("PRRO Receipt", r, "local_number") for r in (r1, r2))
	assert nums == [2, 3], nums  # відкриття=1, чеки=2,3 — наскрізна нумерація
	assert client.sent == ["CHECK", "CHECK", "CHECK", "ZREP", "CHECK"], client.sent

	print(f"OK: shift {shift_name} відкрито→2 чеки→Z-звіт {shift.z_report_fiscal_number}→закрито; "
		  f"local nums {nums}; docs {client.sent}")
	_cleanup(company)
	return "PASS"

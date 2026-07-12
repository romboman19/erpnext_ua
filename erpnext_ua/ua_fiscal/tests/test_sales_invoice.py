"""Тест мапінгу Sales Invoice → фіскальний чек (без запису SI у прод-дані).

Sales Invoice імітується frappe._dict. Перевіряються: мапінг рядків/оплат,
розвʼязання каси/ключа/повʼязаного чека та передача коректних аргументів у
оркестрацію. Виклик orch.fiscalize_sale перехоплюється (без мережі й без
залежності від реального Sales Invoice).

    bench --site <site> execute erpnext_ua.ua_fiscal.tests.test_sales_invoice.run
"""

from unittest.mock import patch

import frappe

from erpnext_ua.ua_fiscal import sales_invoice as si_mod

TESTREG = "_prro_si_test"


def _mock_si(name, is_return=False, return_against=None):
	return frappe._dict({
		"doctype": "Sales Invoice", "name": name, "owner": "Administrator",
		"pos_profile": "_TESTPOS", "is_pos": 1, "is_return": is_return,
		"return_against": return_against, "grand_total": 900.0, "rounded_total": 900.0,
		"change_amount": 100.0,
		"items": [frappe._dict({"item_code": "NOZH-1", "item_name": "Ніж «Ведмідь»", "uom": "шт",
								"stock_uom": "шт", "qty": 2, "rate": 450.0, "amount": 900.0})],
		"payments": [frappe._dict({"mode_of_payment": "Готівка", "type": "Cash", "amount": 900.0})],
	})


def _cleanup():
	for n in frappe.get_all("PRRO Receipt", filters={"cash_register": TESTREG}, pluck="name"):
		frappe.delete_doc("PRRO Receipt", n, force=True)
	frappe.db.commit()


def run():
	frappe.set_user("Administrator")
	_cleanup()

	sale_si = _mock_si("SI-TEST-001")
	ret_si = _mock_si("SI-TEST-002", is_return=True, return_against="SI-TEST-001")

	# 1) мапінг рядків та оплат
	lines = si_mod._invoice_lines(sale_si)
	pays = si_mod._invoice_payments(sale_si)
	assert lines[0]["name"] == "Ніж «Ведмідь»" and lines[0]["amount"] == 900.0, lines
	assert pays[0]["code"] == 0 and pays[0]["remains"] == 100.0, pays
	# картка → код 1
	card_si = _mock_si("x")
	card_si.payments = [frappe._dict({"mode_of_payment": "Картка", "type": "Bank", "amount": 900.0})]
	card_si.change_amount = 0
	assert si_mod._invoice_payments(card_si)[0]["code"] == 1
	print(f"1. Мапінг OK: рядків={len(lines)}, готівка код=0 решта={pays[0]['remains']}, картка код=1")

	# фікстура: «попередній» чек продажу для SI-TEST-001 (ignore_links — SI несправжній)
	prior = frappe.get_doc({
		"doctype": "PRRO Receipt", "cash_register": TESTREG, "shift": None,
		"receipt_type": "Продаж", "status": "Fiscalized", "sales_invoice": "SI-TEST-001",
		"fiscal_number": "5000000001", "total_amount": 900.0,
	})
	prior.flags.ignore_links = True
	prior.flags.ignore_mandatory = True
	prior.insert(ignore_permissions=True)
	frappe.db.commit()

	captured = {}

	def fake_fiscalize_sale(**kwargs):
		captured.update(kwargs)
		return "FAKE-RECEIPT"

	real_get_doc = frappe.get_doc

	def fake_get_doc(*a, **k):
		if a and a[0] == "Sales Invoice":
			return {"SI-TEST-001": sale_si, "SI-TEST-002": ret_si}[a[1]]
		return real_get_doc(*a, **k)

	# 2) ідемпотентність: для SI-TEST-001 вже є фіскалізований чек → повертається він
	with patch.object(si_mod.orch, "fiscalize_sale", side_effect=fake_fiscalize_sale), \
		 patch("frappe.get_doc", side_effect=fake_get_doc):
		assert si_mod.fiscalize_invoice("SI-TEST-001") == prior.name
		assert not captured, "не мав викликати fiscalize_sale для вже фіскалізованого"
		print(f"2. Ідемпотентність OK: повернуто наявний чек {prior.name}")

		# 3) повернення → правильні аргументи в оркестрацію
		with patch.object(si_mod, "_register_for_invoice", return_value=TESTREG), \
			 patch.object(si_mod, "_kep_key_for_invoice", return_value="dummy-key"):
			result = si_mod.fiscalize_invoice("SI-TEST-002")

	assert result == "FAKE-RECEIPT"
	assert captured["receipt_type"] == "Повернення", captured["receipt_type"]
	assert captured["related_receipt"] == prior.name, captured["related_receipt"]
	assert captured["cash_register"] == TESTREG and captured["total"] == 900.0
	assert captured["items"][0]["name"] == "Ніж «Ведмідь»"
	assert captured["payments"][0]["code"] == 0
	print(f"3. Повернення OK: тип={captured['receipt_type']}, "
		  f"повʼязано з {captured['related_receipt']}, сума={captured['total']}")

	print("\nВСІ КРОКИ OK")
	_cleanup()
	return "PASS"

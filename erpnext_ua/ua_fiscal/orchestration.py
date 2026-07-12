"""Оркестрація зміни ПРРО: відкриття → чеки → Z-звіт → закриття.

Онлайн-потік (ЄВПЕЗ): кожен документ формується (check01/zrep01), підписується
через prro-signer, надсилається на `/doc`, у відповідь — квитанція (ticket01)
з фіскальним номером. Локальна нумерація наскрізна в межах каси.

Мережеві виклики ізольовані у FiscalClient; функції приймають `client` для
підстановки в тестах (dependency injection).
"""

import re
import xml.etree.ElementTree as ET

import frappe

from erpnext_ua.ua_fiscal import xml_builder as xb
from erpnext_ua.ua_fiscal.fiscal_client import FiscalClient, FiscalServerError

# Коди форм оплати ДПС
PAYFORM_CASH = 0
PAYFORM_CARD = 1


def parse_ticket(response: bytes) -> dict:
	"""Витягує квитанцію (ticket01) з відповіді сервера (attached CMS або plain XML)."""
	m = re.search(rb"<TICKET[\s>].*?</TICKET>", response, re.S)
	if not m:
		raise FiscalServerError(f"Квитанцію не знайдено у відповіді: {response[:200]!r}")
	root = ET.fromstring(m.group(0).decode("windows-1251", errors="replace"))

	def g(tag):
		el = root.find(tag)
		return el.text if el is not None else None

	code = int(g("ERRORCODE") or 0)
	if code != 0:
		raise FiscalServerError(f"Фіскальний сервер ERRORCODE={code}: {g('ERRORTEXT')}")
	return {
		"error_code": code,
		"order_tax_num": g("ORDERTAXNUM"),
		"offline_session_id": g("OFFLINESESSIONID"),
		"offline_seed": g("OFFLINESEED"),
		"order_num": g("ORDERNUM"),
	}


def _fop_dict(fop_profile: str) -> dict:
	return frappe.db.get_value(
		"FOP Profile", fop_profile,
		["fop_full_name", "tax_id", "vat_payer", "vat_number"], as_dict=True,
	)


def _register_dict(register) -> dict:
	return {
		"unit_name": register.unit_name,
		"unit_address": register.unit_address,
		"fiscal_number": register.fiscal_number,
		"local_number": register.next_local_number,  # локальний № каси (CASHDESKNUM)
	}


def _testing_flag(client) -> bool:
	return client.settings.mode == "Тестовий"


def _send(client, xml: bytes, kep_key: str) -> dict:
	"""Валідувати проти XSD + підписати + надіслати + розібрати квитанцію (онлайн)."""
	try:
		xb.validate_document(xml)
	except Exception as e:
		frappe.log_error(f"PRRO XSD validation failed: {e}", "ua_fiscal")
		raise
	signed = client.sign(xml, kep_key)
	return parse_ticket(client.send_document(signed))


def _build_qr(register_fn: str, fiscal_num: str, total, dt) -> str:
	return (
		f"https://cabinet.tax.gov.ua/cashregs/check?id={fiscal_num}"
		f"&fn={register_fn}&sm={frappe.utils.flt(total):.2f}"
		f"&date={dt.strftime('%Y%m%d')}&time={dt.strftime('%H:%M:%S')}"
	)


@frappe.whitelist()
def open_shift(cash_register: str, kep_key: str, client: FiscalClient | None = None) -> str:
	"""Відкриває зміну на касі. Повертає name створеного PRRO Shift."""
	client = client or FiscalClient()
	register = frappe.get_doc("PRRO Cash Register", cash_register)
	if register.current_shift:
		frappe.throw(f"На касі {cash_register} вже відкрито зміну: {register.current_shift}")

	fop = _fop_dict(register.fop_profile)
	cashier = frappe.db.get_value("UA KEP Key", kep_key, "subject_name") or frappe.session.user
	local_number = register.allocate_local_number()

	head = xb.build_check_head(
		doctype=xb.DOCTYPE_OPEN_SHIFT, fop=fop, register=_register_dict(register),
		local_number=local_number, cashier_name=cashier, testing=_testing_flag(client),
	)
	ticket = _send(client, xb.build_service_document(head), kep_key)

	shift = frappe.get_doc({
		"doctype": "PRRO Shift",
		"cash_register": cash_register,
		"cashier": frappe.db.get_value("UA KEP Key", kep_key, "user"),
		"kep_key": kep_key,
		"status": "Open",
		"opened_at": frappe.utils.now_datetime(),
		"opening_fiscal_number": ticket["order_tax_num"],
	})
	shift.insert(ignore_permissions=True)
	frappe.db.set_value("PRRO Cash Register", cash_register, "current_shift", shift.name,
						update_modified=False)
	# TODO(offline): зберегти ticket["offline_session_id"]/["offline_seed"] у полях каси
	# для роботи в офлайн-режимі (діапазон резервних фіскальних номерів).
	frappe.db.commit()
	return shift.name


@frappe.whitelist()
def fiscalize_sale(
	cash_register: str,
	kep_key: str,
	items: list[dict],
	payments: list[dict],
	total: float,
	taxes: list[dict] | None = None,
	receipt_type: str = "Продаж",
	sales_invoice: str | None = None,
	related_receipt: str | None = None,
	client: FiscalClient | None = None,
) -> str:
	"""Фіскалізує чек продажу/повернення. Повертає name PRRO Receipt."""
	client = client or FiscalClient()
	register = frappe.get_doc("PRRO Cash Register", cash_register)
	if not register.current_shift:
		frappe.throw(f"На касі {cash_register} немає відкритої зміни", FiscalServerError)
	shift = frappe.get_doc("PRRO Shift", register.current_shift)
	if shift.status != "Open":
		frappe.throw(f"Зміна {shift.name} має статус {shift.status}", FiscalServerError)

	fop = _fop_dict(register.fop_profile)
	cashier = frappe.db.get_value("UA KEP Key", kep_key, "subject_name") or frappe.session.user
	local_number = register.allocate_local_number()
	subtype = xb.SUBTYPE_RETURN if receipt_type == "Повернення" else xb.SUBTYPE_GOODS

	related_fiscal = None
	if related_receipt:
		related_fiscal = frappe.db.get_value("PRRO Receipt", related_receipt, "fiscal_number")

	dt = frappe.utils.now_datetime()
	head = xb.build_check_head(
		doctype=xb.DOCTYPE_SALE, subtype=subtype, fop=fop, register=_register_dict(register),
		local_number=local_number, cashier_name=cashier, posting_datetime=dt,
		testing=_testing_flag(client),
		order_ret_num=related_fiscal if receipt_type == "Повернення" else None,
	)
	xml = xb.build_sale_check(head, items=items, payments=payments, total=total, taxes=taxes)

	receipt = frappe.get_doc({
		"doctype": "PRRO Receipt",
		"cash_register": cash_register,
		"shift": shift.name,
		"receipt_type": receipt_type,
		"status": "Draft",
		"sales_invoice": sales_invoice,
		"related_receipt": related_receipt,
		"local_number": local_number,
		"total_amount": total,
		"receipt_xml": xml.decode("windows-1251"),
	})
	receipt.insert(ignore_permissions=True)

	try:
		ticket = _send(client, xml, kep_key)
	except Exception as e:
		receipt.db_set("status", "Error", update_modified=False)
		receipt.db_set("error_message", str(e)[:500], update_modified=False)
		frappe.db.commit()
		raise

	receipt.db_set("fiscal_number", ticket["order_tax_num"], update_modified=False)
	receipt.db_set("status", "Fiscalized", update_modified=False)
	receipt.db_set("fiscalized_at", dt, update_modified=False)
	receipt.db_set("qr_data", _build_qr(register.fiscal_number, ticket["order_tax_num"], total, dt),
				   update_modified=False)
	frappe.db.commit()
	return receipt.name


def _shift_totals(shift_name: str) -> dict:
	"""Підсумки зміни для Z-звіту з фіскалізованих чеків."""
	rows = frappe.get_all(
		"PRRO Receipt",
		filters={"shift": shift_name, "status": "Fiscalized"},
		fields=["receipt_type", "total_amount"],
	)
	realiz = {"sum": 0.0, "count": 0, "payforms": []}
	returns = {"sum": 0.0, "count": 0, "payforms": []}
	for r in rows:
		bucket = returns if r.receipt_type == "Повернення" else realiz
		bucket["sum"] += frappe.utils.flt(r.total_amount)
		bucket["count"] += 1
	# спрощено: підсумок однією формою оплати «Готівка»; деталізацію додамо з POS
	if realiz["count"]:
		realiz["payforms"] = [{"code": PAYFORM_CASH, "name": "Готівка", "sum": realiz["sum"]}]
	if returns["count"]:
		returns["payforms"] = [{"code": PAYFORM_CASH, "name": "Готівка", "sum": returns["sum"]}]
	return {"realiz": realiz, "returns": returns}


@frappe.whitelist()
def close_shift(cash_register: str, kep_key: str, client: FiscalClient | None = None) -> str:
	"""Закриває зміну: Z-звіт + технічний документ закриття."""
	client = client or FiscalClient()
	register = frappe.get_doc("PRRO Cash Register", cash_register)
	if not register.current_shift:
		frappe.throw(f"На касі {cash_register} немає відкритої зміни", FiscalServerError)
	shift = frappe.get_doc("PRRO Shift", register.current_shift)

	fop = _fop_dict(register.fop_profile)
	cashier = frappe.db.get_value("UA KEP Key", kep_key, "subject_name") or frappe.session.user
	totals = _shift_totals(shift.name)

	# 1. Z-звіт (zrep01)
	z_local = register.allocate_local_number()
	zrep = xb.build_zrep(
		fop=fop, register=_register_dict(register), local_number=z_local, cashier_name=cashier,
		realiz=totals["realiz"], returns=totals["returns"], testing=_testing_flag(client),
	)
	z_ticket = _send(client, zrep, kep_key)

	# 2. Технічний документ закриття зміни (check01 DOCTYPE=101)
	c_local = register.allocate_local_number()
	head = xb.build_check_head(
		doctype=xb.DOCTYPE_CLOSE_SHIFT, fop=fop, register=_register_dict(register),
		local_number=c_local, cashier_name=cashier, testing=_testing_flag(client),
	)
	_send(client, xb.build_service_document(head), kep_key)

	shift.db_set("status", "Closed", update_modified=False)
	shift.db_set("closed_at", frappe.utils.now_datetime(), update_modified=False)
	shift.db_set("z_report_fiscal_number", z_ticket["order_tax_num"], update_modified=False)
	shift.db_set("z_report_xml", zrep.decode("windows-1251"), update_modified=False)
	shift.db_set("sales_total", totals["realiz"]["sum"], update_modified=False)
	shift.db_set("refunds_total", totals["returns"]["sum"], update_modified=False)
	shift.db_set("receipts_count", totals["realiz"]["count"] + totals["returns"]["count"],
				 update_modified=False)
	frappe.db.set_value("PRRO Cash Register", cash_register, "current_shift", None,
						update_modified=False)
	frappe.db.commit()
	return shift.name

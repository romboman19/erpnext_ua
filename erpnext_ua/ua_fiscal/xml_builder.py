"""Генерація XML документів check01 для фіскального сервера ДПС.

Кодування — windows-1251 (вимога опису АРІ). Структура за check01.xsd
і прикладами з офіційної документації (дзеркало: /home/romboman19/prro_docs).
"""

import uuid
from xml.sax.saxutils import escape

import frappe

# Типи документів (CheckDocumentType)
DOCTYPE_SALE = 0
DOCTYPE_OPEN_SHIFT = 100
DOCTYPE_CLOSE_SHIFT = 101
DOCTYPE_OFFLINE_BEGIN = 102
DOCTYPE_OFFLINE_END = 103

# Розширені типи (CheckDocumentSubType)
SUBTYPE_GOODS = 0
SUBTYPE_RETURN = 1
SUBTYPE_SERVICE_DEPOSIT = 2
SUBTYPE_SERVICE_ISSUE = 4
SUBTYPE_STORNO = 5


def _fmt_sum(value) -> str:
	return f"{frappe.utils.flt(value):.2f}"


def _head_xml(head: dict) -> str:
	"""CHECKHEAD: порядок елементів за XSD."""
	order = [
		"DOCTYPE", "DOCSUBTYPE", "UID", "TIN", "IPN", "ORGNM", "POINTNM",
		"POINTADDR", "ORDERDATE", "ORDERTIME", "ORDERNUM", "CASHDESKNUM",
		"CASHREGISTERNUM", "CASHIER", "VER", "ORDERTAXNUM", "ORDERRETNUM",
		"ORDERSTORNUM", "OFFLINE", "PREVDOCHASH", "TESTING",
	]
	rows = []
	for tag in order:
		val = head.get(tag)
		if val is None or val == "":
			continue
		rows.append(f"<{tag}>{escape(str(val))}</{tag}>")
	return "<CHECKHEAD>" + "".join(rows) + "</CHECKHEAD>"


def build_check_head(
	*,
	doctype: int,
	fop: dict,
	register: dict,
	local_number: int,
	cashier_name: str,
	posting_datetime=None,
	subtype: int | None = None,
	testing: bool = False,
	offline: bool = False,
	prev_doc_hash: str | None = None,
	order_tax_num: str | None = None,
	order_ret_num: str | None = None,
	order_storno_num: str | None = None,
) -> dict:
	dt = posting_datetime or frappe.utils.now_datetime()
	head = {
		"DOCTYPE": doctype,
		"UID": str(uuid.uuid4()).upper(),
		"TIN": fop["tax_id"],
		"ORGNM": f"ФОП {fop['fop_full_name']}",
		"POINTNM": register["unit_name"],
		"POINTADDR": register["unit_address"],
		"ORDERDATE": dt.strftime("%d%m%Y"),
		"ORDERTIME": dt.strftime("%H%M%S"),
		"ORDERNUM": local_number,
		"CASHDESKNUM": register.get("local_number") or 1,
		"CASHREGISTERNUM": register["fiscal_number"],
		"CASHIER": cashier_name,
		"VER": 1,
	}
	if fop.get("vat_payer") and fop.get("vat_number"):
		head["IPN"] = fop["vat_number"]
	if subtype is not None:
		head["DOCSUBTYPE"] = subtype
	if testing:
		head["TESTING"] = "true"
	if offline:
		head["OFFLINE"] = "true"
		head["ORDERTAXNUM"] = order_tax_num
		if prev_doc_hash:
			head["PREVDOCHASH"] = prev_doc_hash
	if order_ret_num:
		head["ORDERRETNUM"] = order_ret_num
	if order_storno_num:
		head["ORDERSTORNUM"] = order_storno_num
	return head


def build_service_document(head: dict) -> bytes:
	"""Технічні документи: відкриття/закриття зміни, початок/кінець офлайн сесії."""
	xml = (
		'<?xml version="1.0" encoding="windows-1251"?>'
		'<CHECK xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
		'xsi:noNamespaceSchemaLocation="check01.xsd">'
		+ _head_xml(head)
		+ "</CHECK>"
	)
	return xml.encode("windows-1251")


def build_sale_check(head: dict, items: list[dict], payments: list[dict], total: float) -> bytes:
	"""Чек реалізації (або повернення — залежно від DOCSUBTYPE у head).

	items: [{code, name, uom, qty, price, amount, letters?}]
	payments: [{code: 0-готівка/1-картка.., name, sum, provided?, remains?}]
	"""
	body_rows = []
	for i, item in enumerate(items, start=1):
		row = [
			f"<ROW ROWNUM=\"{i}\">",
			f"<CODE>{escape(str(item.get('code') or i))}</CODE>",
			f"<NAME>{escape(item['name'])}</NAME>",
			f"<UNITNM>{escape(item.get('uom') or 'шт')}</UNITNM>",
			f"<AMOUNT>{frappe.utils.flt(item['qty']):g}</AMOUNT>",
			f"<PRICE>{_fmt_sum(item['price'])}</PRICE>",
			f"<COST>{_fmt_sum(item['amount'])}</COST>",
		]
		if item.get("letters"):
			row.append(f"<LETTERS>{escape(item['letters'])}</LETTERS>")
		row.append("</ROW>")
		body_rows.append("".join(row))

	pay_rows = []
	for i, pay in enumerate(payments, start=1):
		pay_rows.append(
			f"<ROW ROWNUM=\"{i}\">"
			f"<PAYFORMCD>{pay['code']}</PAYFORMCD>"
			f"<PAYFORMNM>{escape(pay['name'])}</PAYFORMNM>"
			f"<SUM>{_fmt_sum(pay['sum'])}</SUM>"
			+ (f"<PROVIDED>{_fmt_sum(pay['provided'])}</PROVIDED>" if pay.get("provided") is not None else "")
			+ (f"<REMAINS>{_fmt_sum(pay['remains'])}</REMAINS>" if pay.get("remains") is not None else "")
			+ "</ROW>"
		)

	xml = (
		'<?xml version="1.0" encoding="windows-1251"?>'
		'<CHECK xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
		'xsi:noNamespaceSchemaLocation="check01.xsd">'
		+ _head_xml(head)
		+ f"<CHECKTOTAL><SUM>{_fmt_sum(total)}</SUM></CHECKTOTAL>"
		+ "<CHECKPAY>" + "".join(pay_rows) + "</CHECKPAY>"
		+ "<CHECKBODY>" + "".join(body_rows) + "</CHECKBODY>"
		+ "</CHECK>"
	)
	return xml.encode("windows-1251")

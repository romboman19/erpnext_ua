"""Native Print Designer layouts for Ukrainian business documents."""

from __future__ import annotations

from erpnext_ua.print_designer_layout import (
	A4_HEIGHT,
	A4_WIDTH,
	MM_TO_PX,
	dynamic_field,
	layout_row,
	page_settings,
	print_format_document,
	static_jinja_field,
	table_column,
	table_element,
	text_element,
)


SALES_FORMATS = (
	("Рахунок-фактура (UA) (Print Designer)", "Рахунок-фактура", "Найменування товару", "покупця"),
	("Видаткова накладна (UA) (Print Designer)", "Видаткова накладна", "Найменування товару", "покупця"),
	(
		"Акт виконаних робіт (UA) (Print Designer)",
		"Акт наданих послуг (виконаних робіт)",
		"Найменування робіт (послуг)",
		"замовника",
	),
)
RECEIPT_FORMAT_NAME = "Прибуткова накладна (UA) (Print Designer)"


def build_document_formats(base_settings: dict) -> list[dict]:
	formats = [
		_build_sales_format(base_settings, name, title, item_label, recipient)
		for name, title, item_label, recipient in SALES_FORMATS
	]
	formats.append(_build_receipt_format(base_settings))
	return formats


def _build_sales_format(base_settings, name, title, item_label, recipient):
	content_width = A4_WIDTH - (20 * MM_TO_PX)
	settings = _a4_settings(base_settings)
	elements = [
		text_element(
			"sales-title",
			f"{title} № {{{{ doc.name }}}}",
			x=0,
			y=0,
			width=content_width,
			height=34,
			font_size="14pt",
			font_weight=700,
			text_align="center",
			parse_jinja=True,
			classes=("ua-pd-title",),
			index=0,
		),
		text_element(
			"sales-date",
			'від {{ frappe.utils.formatdate(doc.posting_date if doc.get("posting_date") else doc.transaction_date, "dd.MM.yyyy") }} р.',
			x=0,
			y=38,
			width=content_width,
			height=24,
			font_size="10pt",
			text_align="center",
			parse_jinja=True,
			index=1,
		),
		text_element(
			"sales-supplier",
			_SUPPLIER_BLOCK,
			x=0,
			y=76,
			width=content_width,
			height=76,
			parse_jinja=True,
			classes=("ua-pd-party",),
			index=2,
		),
		text_element(
			"sales-customer",
			_CUSTOMER_BLOCK,
			x=0,
			y=160,
			width=content_width,
			height=44,
			parse_jinja=True,
			classes=("ua-pd-party",),
			index=3,
		),
	]
	items_table = _sales_items_table(content_width, item_label, index=4)
	elements.append(items_table)
	elements.extend(
		[
			text_element(
				"sales-totals",
				_SALES_TOTALS,
				x=content_width * 0.45,
				y=480,
				width=content_width * 0.55,
				height=92,
				text_align="right",
				parse_jinja=True,
				classes=("ua-pd-totals",),
				index=5,
			),
			_signature("sales-sign-supplier", "Від постачальника", x=0, y=610, width=content_width * 0.44, index=6),
			_signature(
				"sales-sign-recipient",
				f"Від {recipient}",
				x=content_width * 0.56,
				y=610,
				width=content_width * 0.44,
				index=7,
			),
		]
	)
	layout_rows = [
		layout_row("sales-row-title", [elements[0]], width=content_width, height=38),
		layout_row("sales-row-date", [elements[1]], width=content_width, height=32),
		layout_row("sales-row-supplier", [elements[2]], width=content_width, height=76, height_type="auto", child_top=8),
		layout_row("sales-row-customer", [elements[3]], width=content_width, height=44, height_type="auto", child_top=8),
		layout_row("sales-row-items", [items_table], width=content_width, height=250, height_type="auto", child_top=12),
		layout_row("sales-row-totals", [elements[5]], width=content_width, height=92, height_type="auto", child_top=12),
		layout_row("sales-row-signatures", elements[6:8], width=content_width, height=110, child_top=22),
	]
	return print_format_document(
		name=name,
		doc_type="Sales Invoice",
		module="UA FOP",
		settings=settings,
		elements=elements,
		layout_rows=layout_rows,
		css=_DOCUMENT_CSS,
	)


def _build_receipt_format(base_settings):
	content_width = A4_WIDTH - (20 * MM_TO_PX)
	settings = _a4_settings(base_settings)
	elements = [
		text_element(
			"receipt-title",
			"Прибуткова накладна",
			x=0,
			y=0,
			width=content_width,
			height=34,
			font_size="15pt",
			font_weight=700,
			text_align="center",
			index=0,
		),
		text_element(
			"receipt-subtitle",
			'№ {{ doc.name }} від {{ frappe.utils.formatdate(doc.posting_date, "dd.MM.yyyy") }}',
			x=0,
			y=38,
			width=content_width,
			height=24,
			text_align="center",
			parse_jinja=True,
			index=1,
		),
		text_element(
			"receipt-state",
			_RECEIPT_STATE,
			x=0,
			y=70,
			width=content_width,
			height=42,
			font_weight=700,
			text_align="center",
			parse_jinja=True,
			classes=("ua-pd-state",),
			index=2,
		),
		text_element(
			"receipt-meta",
			_RECEIPT_META,
			x=0,
			y=124,
			width=content_width,
			height=120,
			parse_jinja=True,
			classes=("ua-pd-meta",),
			index=3,
		),
	]
	items_table = _receipt_items_table(content_width, index=4)
	elements.append(items_table)
	elements.extend(
		[
			text_element(
				"receipt-summary",
				_RECEIPT_SUMMARY,
				x=content_width * 0.5,
				y=575,
				width=content_width * 0.5,
				height=94,
				text_align="right",
				parse_jinja=True,
				classes=("ua-pd-totals",),
				index=5,
			),
			text_element(
				"receipt-vat-note",
				_RECEIPT_VAT_NOTE,
				x=0,
				y=682,
				width=content_width,
				height=48,
				font_size="8pt",
				parse_jinja=True,
				classes=("ua-pd-vat-note",),
				index=6,
			),
		]
	)
	signature_width = content_width * 0.29
	for index, (element_id, label, x) in enumerate(
		(
			("receipt-sign-sender", "Відвантажив", 0),
			("receipt-sign-receiver", "Прийняв", content_width * 0.355),
			("receipt-sign-verifier", "Перевірив", content_width * 0.71),
		),
		start=7,
	):
		elements.append(_signature(element_id, label, x=x, y=760, width=signature_width, index=index))
	layout_rows = [
		layout_row("receipt-row-title", [elements[0]], width=content_width, height=38),
		layout_row("receipt-row-subtitle", [elements[1]], width=content_width, height=32),
		layout_row("receipt-row-state", [elements[2]], width=content_width, height=52, child_top=6),
		layout_row("receipt-row-meta", [elements[3]], width=content_width, height=120, height_type="auto", child_top=10),
		layout_row("receipt-row-items", [items_table], width=content_width, height=300, height_type="auto", child_top=14),
		layout_row("receipt-row-summary", [elements[5]], width=content_width, height=94, height_type="auto", child_top=14),
		layout_row("receipt-row-vat", [elements[6]], width=content_width, height=48, height_type="auto", child_top=8),
		layout_row("receipt-row-signatures", elements[7:10], width=content_width, height=112, child_top=24),
	]
	return print_format_document(
		name=RECEIPT_FORMAT_NAME,
		doc_type="Purchase Receipt",
		module="UA Receiving",
		settings=settings,
		elements=elements,
		layout_rows=layout_rows,
		css=_DOCUMENT_CSS,
	)


def _sales_items_table(width, item_label, *, index):
	columns = [
		table_column(0, "№", 5, [dynamic_field("idx", "Int", "№", table_name="items")], style={"textAlign": "center"}),
		table_column(1, item_label, 46, [dynamic_field("item_name", "Data", item_label, table_name="items")]),
		table_column(2, "Од.", 10, [dynamic_field("uom", "Link", "Од.", table_name="items")], style={"textAlign": "center"}),
		table_column(3, "К-сть", 10, [dynamic_field("qty", "Float", "К-сть", table_name="items")], style={"textAlign": "right"}),
		table_column(4, "Ціна, грн", 14, [dynamic_field("rate", "Currency", "Ціна", table_name="items")], style={"textAlign": "right"}),
		table_column(5, "Сума, грн", 15, [dynamic_field("amount", "Currency", "Сума", table_name="items")], style={"textAlign": "right"}),
	]
	return table_element(
		"sales-items",
		table_fieldname="items",
		table_label="Позиції",
		table_options="Sales Invoice Item",
		columns=columns,
		x=0,
		y=218,
		width=width,
		height=240,
		classes=("ua-pd-items",),
		index=index,
	)


def _receipt_items_table(width, *, index):
	columns = [
		table_column(0, "№", 4, [dynamic_field("idx", "Int", "№", table_name="items")], style={"textAlign": "center"}),
		table_column(1, "Найменування товару", 29, [static_jinja_field('<b>{{ row.item_name or row.item_code }}</b><br><span class="ua-muted">{{ row.item_code }}</span>{% if row.warehouse %}<br><span class="ua-muted">{{ row.warehouse }}</span>{% endif %}')]),
		table_column(2, "Штрихкод", 13, [static_jinja_field('{{ row.barcode or frappe.db.get_value("Item Barcode", {"parent": row.item_code}, "barcode") or "—" }}')], style={"textAlign": "center"}),
		table_column(3, "Од.", 7, [static_jinja_field('{{ row.uom or row.stock_uom }}')], style={"textAlign": "center"}),
		table_column(4, "К-сть", 7, [dynamic_field("qty", "Float", "К-сть", table_name="items")], style={"textAlign": "right"}),
		table_column(5, "Закуп. ціна, грн", 12, [dynamic_field("rate", "Currency", "Ціна", table_name="items")], style={"textAlign": "right"}),
		table_column(6, "Сума, грн", 13, [dynamic_field("amount", "Currency", "Сума", table_name="items")], style={"textAlign": "right"}),
		table_column(7, "Факт", 7, [static_jinja_field("&nbsp;")]),
		table_column(8, "Примітка", 8, [static_jinja_field("&nbsp;")]),
	]
	return table_element(
		"receipt-items",
		table_fieldname="items",
		table_label="Товари",
		table_options="Purchase Receipt Item",
		columns=columns,
		x=0,
		y=260,
		width=width,
		height=290,
		classes=("ua-pd-items", "ua-pd-receipt-items"),
		index=index,
	)


def _signature(element_id, label, *, x, y, width, index):
	return text_element(
		element_id,
		f'<b>{label}</b><span class="ua-signature-line">&nbsp;</span><span class="ua-signature-hint">підпис, ПІБ</span>',
		x=x,
		y=y,
		width=width,
		height=76,
		classes=("ua-pd-signature",),
		index=index,
	)


def _a4_settings(base_settings):
	return page_settings(
		base_settings,
		width=A4_WIDTH,
		height=A4_HEIGHT,
		margin_top=12 * MM_TO_PX,
		margin_bottom=13 * MM_TO_PX,
		margin_left=10 * MM_TO_PX,
		margin_right=10 * MM_TO_PX,
		page_size="A4",
	)


_SUPPLIER_BLOCK = """
{% set fop = frappe.db.get_value("FOP Profile", {"company": doc.company}, ["fop_full_name", "tax_id", "iban", "bank_name", "registration_address", "vat_payer", "vat_number"], as_dict=True) %}
<b>Постачальник:</b> {% if fop %}ФОП {{ fop.fop_full_name }}, РНОКПП {{ fop.tax_id }}{% if fop.vat_payer %}, ІПН платника ПДВ {{ fop.vat_number }}{% endif %}<br>{% if fop.registration_address %}{{ fop.registration_address }}<br>{% endif %}{% if fop.iban %}IBAN: {{ fop.iban }}{% if fop.bank_name %}, {{ fop.bank_name }}{% endif %}{% endif %}{% else %}{{ doc.company }}{% endif %}
""".strip()

_CUSTOMER_BLOCK = """
<b>Покупець:</b> {{ doc.customer_name or doc.customer }}{% if doc.tax_id %}, код {{ doc.tax_id }}{% endif %}{% if doc.address_display %}<br>{{ doc.address_display|striptags }}{% endif %}
""".strip()

_SALES_TOTALS = """
{% if doc.total_taxes_and_charges %}Разом без ПДВ: <b>{{ doc.get_formatted("net_total") }}</b><br>ПДВ: <b>{{ doc.get_formatted("total_taxes_and_charges") }}</b><br>{% endif %}<span class="ua-total">Всього до сплати: <b>{{ doc.get_formatted("grand_total") }}</b></span><br>Сума прописом: {{ doc.in_words or frappe.utils.money_in_words(doc.grand_total, doc.currency) }}
""".strip()

_RECEIPT_STATE = """
{% if doc.docstatus == 0 %}КОНТРОЛЬНИЙ ЛИСТ — ЧЕРНЕТКА. Товар ще не оприбутковано.{% elif doc.docstatus == 1 %}ПРОВЕДЕНО. Товар оприбутковано на склад.{% else %}СКАСОВАНО. Документ не формує чинного залишку.{% endif %}
""".strip()

_RECEIPT_META = """
{% set supplier = frappe.db.get_value("Supplier", doc.supplier, ["supplier_name", "tax_id"], as_dict=True) %}{% set warehouse = doc.set_warehouse or (doc.items[0].warehouse if doc.items else "") %}
<span class="ua-meta-column"><span class="ua-muted">Постачальник:</span><br><b>{{ doc.supplier_name or (supplier.supplier_name if supplier else doc.supplier) }}</b>{% if supplier and supplier.tax_id %}<br>Код: {{ supplier.tax_id }}{% endif %}{% if doc.address_display %}<br>{{ doc.address_display|striptags }}{% endif %}<br><br><span class="ua-muted">Документ постачальника:</span> {{ doc.ua_supplier_document_type or "—" }}<br><span class="ua-muted">Номер:</span> {{ doc.supplier_delivery_note or "—" }}</span>
<span class="ua-meta-column"><span class="ua-muted">Одержувач:</span><br><b>{{ doc.company }}</b><br><span class="ua-muted">Склад:</span> {{ warehouse or "—" }}<br><br><span class="ua-muted">Дата документа:</span> {{ frappe.utils.formatdate(doc.ua_supplier_document_date, "dd.MM.yyyy") if doc.ua_supplier_document_date else "—" }}<br><span class="ua-muted">Прийняв:</span> {{ doc.ua_received_by or "—" }}</span>
""".strip()

_RECEIPT_SUMMARY = """
Усього позицій: <b>{{ doc.items|length }}</b><br>Загальна кількість: <b>{{ doc.get_formatted("total_qty") }}</b><br>{% if doc.total_taxes_and_charges %}Податки та витрати: <b>{{ doc.get_formatted("total_taxes_and_charges") }}</b><br>{% endif %}<span class="ua-total">Разом: <b>{{ doc.get_formatted("grand_total") }}</b></span>
""".strip()

_RECEIPT_VAT_NOTE = """
{% if doc.ua_add_vat_20_to_prices %}До введених цін постачальника додано 20%. Повна ціна включена у вартість товару без окремого податкового рядка та податкової проводки.{% endif %}
""".strip()

_DOCUMENT_CSS = """
@page { size: A4; margin: 12mm 10mm 13mm; }
.print-format { margin: 0 !important; padding: 0 !important; }
#__print_designer { color: #111; font-family: "DejaVu Sans", sans-serif; }
.staticText { margin: 0 !important; }
.ua-pd-title { letter-spacing: .01em; }
.ua-pd-party { line-height: 1.35 !important; }
.ua-pd-state { box-sizing: border-box; padding: 2.2mm 3mm !important; border: 1px solid #333 !important; background: #f4f4f4 !important; }
.ua-pd-meta .ua-meta-column { display: inline-block; box-sizing: border-box; width: 49%; padding-right: 4mm; vertical-align: top; }
.ua-muted { color: #555; font-size: 8pt; font-weight: 400; }
.ua-pd-items { border-collapse: collapse !important; table-layout: fixed; }
.ua-pd-items th, .ua-pd-items td { overflow-wrap: anywhere; }
.ua-pd-receipt-items td:nth-child(8), .ua-pd-receipt-items td:nth-child(9) { height: 8mm; }
.ua-pd-totals { line-height: 1.45 !important; }
.ua-total { font-size: 11pt; }
.ua-pd-vat-note { box-sizing: border-box; padding: 2mm !important; border-left: 3px solid #444 !important; background: #f5f5f5 !important; }
.ua-signature-line { display: block; height: 9mm; border-bottom: 1px solid #222; }
.ua-signature-hint { display: block; color: #555; font-size: 7pt; text-align: center; }
""".strip()

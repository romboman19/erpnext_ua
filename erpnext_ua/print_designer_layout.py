"""Small builders for native Print Designer format documents."""

from __future__ import annotations

import json
from copy import deepcopy


A4_WIDTH = 793.701
A4_HEIGHT = 1122.52
MM_TO_PX = 96 / 25.4


def page_settings(
	base_settings: dict,
	*,
	width: float,
	height: float,
	margin_top: float = 0,
	margin_bottom: float = 0,
	margin_left: float = 0,
	margin_right: float = 0,
	page_size: str = "CUSTOM",
	user_jinja: str = "",
) -> dict:
	settings = deepcopy(base_settings)
	settings["page"] = {
		"UOM": "mm",
		"footerHeight": 0,
		"footerHeightWithMargin": margin_bottom,
		"headerHeight": 0,
		"headerHeightWithMargin": margin_top,
		"height": height,
		"marginBottom": margin_bottom,
		"marginLeft": margin_left,
		"marginRight": margin_right,
		"marginTop": margin_top,
		"width": width,
	}
	settings.update(
		{
			"currentPageSize": page_size,
			"currentDoc": "",
			"currentFonts": [],
			"isHeaderFooterAuto": False,
			"pdfPrintDPI": 96,
			"printBodyFonts": {},
			"printFooterFonts": {},
			"printHeaderFonts": {},
			"textControlType": "dynamic",
			"userProvidedJinja": user_jinja,
		}
	)
	return settings


def text_element(
	element_id: str,
	content: str,
	*,
	x: float,
	y: float,
	width: float,
	height: float,
	font_size: str = "10pt",
	font_weight: int = 400,
	text_align: str = "left",
	parse_jinja: bool = False,
	classes: tuple[str, ...] = (),
	index: int = 0,
) -> dict:
	return {
		"id": element_id,
		"type": "text",
		"content": content,
		"contenteditable": False,
		"isDynamic": False,
		"isFixedSize": True,
		"isDraggable": True,
		"isResizable": True,
		"isDropZone": False,
		"parseJinja": parse_jinja,
		"startX": x,
		"startY": y,
		"width": width,
		"height": height,
		"styleEditMode": "main",
		"labelDisplayStyle": "standard",
		"style": {
			"color": "#000000",
			"fontFamily": "DejaVu Sans",
			"fontSize": font_size,
			"fontWeight": font_weight,
			"lineHeight": 1.25,
			"margin": "0px",
			"overflow": "hidden",
			"paddingBottom": "0px",
			"paddingLeft": "0px",
			"paddingRight": "0px",
			"paddingTop": "0px",
			"textAlign": text_align,
			"whiteSpace": "normal",
			"zIndex": 0,
		},
		"classes": list(classes),
		"isElementOverlapping": False,
		"heightType": "fixed",
		"isDynamicHeight": False,
		"index": index,
	}


def dynamic_field(
	fieldname: str,
	fieldtype: str,
	label: str,
	*,
	table_name: str,
	next_line: bool = False,
	style: dict | None = None,
) -> dict:
	return {
		"doctype": "",
		"parentField": "",
		"fieldname": fieldname,
		"value": "",
		"fieldtype": fieldtype,
		"label": label,
		"suffix": None,
		"is_labelled": False,
		"is_static": False,
		"print_hide": 0,
		"style": style or {},
		"tableName": table_name,
		"labelStyle": {},
		"nextLine": next_line,
		"labelStyleEditing": False,
	}


def static_jinja_field(value: str, *, style: dict | None = None) -> dict:
	return {
		"doctype": "",
		"parentField": "",
		"fieldname": "designer_static_value",
		"value": value,
		"fieldtype": "StaticText",
		"is_static": True,
		"is_labelled": False,
		"nextLine": False,
		"parseJinja": True,
		"style": style or {},
		"labelStyle": {},
		"labelStyleEditing": False,
	}


def table_column(
	column_id: int,
	label: str,
	width: float,
	fields: list[dict],
	*,
	style: dict | None = None,
) -> dict:
	return {
		"id": column_id,
		"label": label,
		"style": style or {},
		"applyStyleToHeader": True,
		"dynamicContent": fields,
		"width": width,
		"selectedDynamicText": None,
	}


def table_element(
	element_id: str,
	*,
	table_fieldname: str,
	table_label: str,
	table_options: str,
	columns: list[dict],
	x: float,
	y: float,
	width: float,
	height: float,
	classes: tuple[str, ...] = (),
	index: int = 0,
	style: dict | None = None,
	header_style: dict | None = None,
) -> dict:
	return {
		"id": element_id,
		"type": "table",
		"isDraggable": True,
		"isResizable": True,
		"isDropZone": False,
		"table": {
			"fieldname": table_fieldname,
			"fieldtype": "Table",
			"label": table_label,
			"options": table_options,
			"print_hide": 0,
		},
		"columns": columns,
		"PreviewRowNo": 1,
		"selectedColumn": None,
		"selectedDynamicText": None,
		"startX": x,
		"startY": y,
		"width": width,
		"height": height,
		"styleEditMode": "main",
		"labelDisplayStyle": "standard",
		"style": style or _table_style(),
		"labelStyle": {},
		"headerStyle": header_style or _table_header_style(),
		"altStyle": {},
		"classes": list(classes),
		"isElementOverlapping": False,
		"heightType": "auto",
		"isDynamicHeight": False,
		"index": index,
	}


def layout_row(
	row_id: str,
	elements: list[dict],
	*,
	width: float,
	height: float,
	height_type: str = "fixed",
	start_y: float = 0,
	child_top: float = 0,
) -> dict:
	children = deepcopy(elements)
	for child in children:
		child["startY"] = child_top
	return {
		"id": row_id,
		"type": "rectangle",
		"childrens": children,
		"isDraggable": False,
		"isResizable": False,
		"isDropZone": False,
		"startX": 0,
		"startY": start_y,
		"width": width,
		"height": height,
		"styleEditMode": "main",
		"style": {},
		"classes": ["relative-row"],
		"layoutType": "row",
		"heightType": height_type,
	}


def print_format_document(
	*,
	name: str,
	doc_type: str,
	module: str,
	settings: dict,
	elements: list[dict],
	layout_rows: list[dict],
	css: str,
) -> dict:
	header_footer_page = {
		"type": "page",
		"childrens": [],
		"firstPage": True,
		"oddPage": True,
		"evenPage": True,
		"lastPage": True,
	}
	editor_body = [{"type": "page", "index": 0, "isDropZone": True, "childrens": elements}]
	print_body = [{"type": "page", "index": 0, "childrens": layout_rows}]
	print_layout = {
		"header": {"firstPage": [], "oddPage": [], "evenPage": [], "lastPage": []},
		"body": print_body,
		"footer": {"firstPage": [], "oddPage": [], "evenPage": [], "lastPage": []},
	}
	return {
		"doctype": "Print Format",
		"name": name,
		"doc_type": doc_type,
		"module": module,
		"standard": "No",
		"custom_format": 0,
		"disabled": 0,
		"print_format_type": "Jinja",
		"raw_printing": 0,
		"print_designer": 1,
		"print_designer_header": _json([header_footer_page]),
		"print_designer_body": _json(editor_body),
		"print_designer_after_table": "[]",
		"print_designer_footer": _json([header_footer_page]),
		"print_designer_print_format": _json(print_layout),
		"print_designer_settings": _json(settings),
		"css": css,
		"font_size": 10,
		"line_breaks": 0,
		"margin_top": 0,
		"margin_bottom": 0,
		"margin_left": 0,
		"margin_right": 0,
		"page_number": "Hide",
		"show_section_headings": 0,
	}


def _table_style() -> dict:
	return {
		"backgroundColor": "#ffffff",
		"borderColor": "#000000",
		"borderStyle": "solid",
		"borderWidth": "1px",
		"color": "#000000",
		"fontFamily": "DejaVu Sans",
		"fontSize": "9pt",
		"lineHeight": 1.2,
		"paddingBottom": "5px",
		"paddingLeft": "5px",
		"paddingRight": "5px",
		"paddingTop": "5px",
		"verticalAlign": "middle",
	}


def _table_header_style() -> dict:
	style = _table_style()
	style.update({"backgroundColor": "#ededed", "fontSize": "8pt", "fontWeight": 600})
	return style


def _json(value) -> str:
	return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

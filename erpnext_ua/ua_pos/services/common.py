from __future__ import annotations

import hashlib
import json

import frappe


SESSION_TTL = 12 * 60 * 60


def digest(value: str) -> str:
	return hashlib.sha256(value.encode("utf-8")).hexdigest()


def session_key(token: str) -> str:
	return f"ua_pos:session:{digest(token)}"


def get_session(token: str | None) -> dict:
	if not token:
		frappe.throw("POS session token is required", frappe.PermissionError)
	data = frappe.cache.get_value(session_key(token))
	if not data:
		frappe.throw("POS session expired", frappe.PermissionError)
	if isinstance(data, str):
		data = json.loads(data)
	frappe.cache.expire(session_key(token), SESSION_TTL)
	return data


def audit(event_type: str, session: dict | None = None, reference=None, details=None, reason=None):
	payload = {
		"doctype": "POS Event Log",
		"event_type": event_type,
		"event_at": frappe.utils.now_datetime(),
		"user": frappe.session.user,
		"employee": (session or {}).get("employee"),
		"cash_desk": (session or {}).get("cash_desk"),
		"details_json": frappe.as_json(details or {}),
		"reason": reason,
	}
	if reference:
		payload["reference_doctype"], payload["reference_name"] = reference
	frappe.get_doc(payload).insert(ignore_permissions=True)


def active_shift(cash_desk: str, *, for_update: bool = False):
	query = """select name from `tabPOS Operational Shift`
		where cash_desk=%s and status in ('Open', 'Closing') order by creation desc limit 1"""
	if for_update:
		query += " for update"
	rows = frappe.db.sql(query, cash_desk)
	return rows[0][0] if rows else None


def parse_rows(value) -> list[dict]:
	if isinstance(value, str):
		value = frappe.parse_json(value)
	return list(value or [])


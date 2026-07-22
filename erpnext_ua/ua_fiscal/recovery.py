"""Періодичне безпечне відновлення offline та невизначених операцій ПРРО."""

from __future__ import annotations

import frappe

from erpnext_ua.ua_fiscal.fiscal_client import FiscalClient
from erpnext_ua.ua_fiscal.orchestration import (
	_shift_totals,
	end_offline_session,
	flush_offline_session,
	reconcile_receipt,
)


def _repair_closing_shift(shift_name: str):
	shift = frappe.get_doc("PRRO Shift", shift_name)
	if shift.status != "Closing":
		return
	z = frappe.get_all(
		"PRRO Receipt",
		filters={"shift": shift.name, "receipt_kind": "Z Report"},
		fields=["status", "fiscal_number", "receipt_xml"],
		order_by="local_number desc",
		limit=1,
	)
	close = frappe.get_all(
		"PRRO Receipt",
		filters={"shift": shift.name, "receipt_kind": "Close Shift"},
		fields=["status", "fiscal_number", "local_number"],
		order_by="local_number desc",
		limit=1,
	)
	if not z or not close or z[0].status != "Fiscalized" or close[0].status != "Fiscalized":
		return
	totals = _shift_totals(shift.name)
	frappe.db.set_value(
		"PRRO Shift",
		shift.name,
		{
			"status": "Closed",
			"closed_at": frappe.utils.now_datetime(),
			"closing_fiscal_number": close[0].fiscal_number,
			"closing_local_number": close[0].local_number,
			"z_report_fiscal_number": z[0].fiscal_number,
			"z_report_xml": z[0].receipt_xml,
			"sales_total": totals["realiz"]["sum"],
			"refunds_total": totals["returns"]["sum"],
			"receipts_count": totals["realiz"]["count"] + totals["returns"]["count"],
		},
		update_modified=False,
	)
	frappe.db.set_value(
		"PRRO Cash Register",
		{"current_shift": shift.name},
		{"current_shift": None, "runtime_state": "Online"},
		update_modified=False,
	)
	frappe.db.commit()


def _acquire_lock() -> bool:
	return bool(frappe.db.sql("select get_lock('erpnext_ua_prro_recovery', 0)")[0][0])


def _release_lock():
	frappe.db.sql("select release_lock('erpnext_ua_prro_recovery')")


def recover_fiscal_state():
	settings = frappe.get_single("PRRO Settings")
	if not settings.enabled or not settings.offline_auto_recovery or not _acquire_lock():
		return
	try:
		client = FiscalClient(settings=settings)
		try:
			client.server_state()
		except Exception:
			return

		for name in frappe.get_all(
			"PRRO Offline Session",
			filters={
				"status": ("in", ("Open", "Queued", "Error")),
				"next_retry_at": ("is", "not set"),
			},
			pluck="name",
		):
			try:
				session = frappe.get_doc("PRRO Offline Session", name)
				if session.status == "Open":
					session = end_offline_session(name, client)
				flush_offline_session(session.name, client)
			except Exception:
				frappe.log_error(frappe.get_traceback(), f"PRRO offline recovery {name}")

		due_errors = frappe.get_all(
			"PRRO Offline Session",
			filters={"status": "Error", "next_retry_at": ("<=", frappe.utils.now_datetime())},
			pluck="name",
		)
		for name in due_errors:
			try:
				flush_offline_session(name, client)
			except Exception:
				frappe.log_error(frappe.get_traceback(), f"PRRO offline retry {name}")

		for name in frappe.get_all("PRRO Receipt", filters={"status": "Uncertain", "is_offline": 0}, pluck="name"):
			try:
				reconcile_receipt(name, client)
			except Exception:
				frappe.log_error(frappe.get_traceback(), f"PRRO reconcile {name}")

		for shift in frappe.get_all("PRRO Shift", filters={"status": "Closing"}, pluck="name"):
			_repair_closing_shift(shift)

		from erpnext_ua.ua_pos.api import recover_pos_fiscal_pending

		recover_pos_fiscal_pending()
	finally:
		_release_lock()

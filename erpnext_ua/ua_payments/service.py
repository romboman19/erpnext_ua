"""Create traceable Payment Entry drafts from Purchase Invoices."""

from __future__ import annotations

import hashlib
import json

import frappe
from frappe import _
from frappe.realtime import get_user_room
from frappe.utils import flt
from frappe.utils.synchronization import filelock


COMPLETION_EVENT = "erpnext_ua_payment_entries_created"
MAX_INVOICES = 100


def _normalize_invoice_names(invoice_names: str | list[str]) -> list[str]:
	if isinstance(invoice_names, str):
		try:
			invoice_names = json.loads(invoice_names)
		except json.JSONDecodeError:
			invoice_names = [invoice_names]

	if not isinstance(invoice_names, list):
		frappe.throw(_("Некоректний список рахунків постачальника"))

	normalized = []
	for value in invoice_names:
		if not isinstance(value, str) or not value.strip():
			frappe.throw(_("Некоректний номер рахунку постачальника"))
		name = value.strip()
		if name not in normalized:
			normalized.append(name)

	if not normalized:
		frappe.throw(_("Виберіть хоча б один рахунок постачальника"))
	if len(normalized) > MAX_INVOICES:
		frappe.throw(_("За один раз можна обробити не більше {0} рахунків").format(MAX_INVOICES))

	return sorted(normalized)


def _job_id(invoice_names: list[str], user: str) -> str:
	payload = f"{user}|{'|'.join(invoice_names)}".encode()
	digest = hashlib.sha1(payload, usedforsecurity=False).hexdigest()[:20]
	return f"ua-payment-entries-{digest}"


def _lock_name(invoice_name: str) -> str:
	digest = hashlib.sha1(invoice_name.encode(), usedforsecurity=False).hexdigest()
	return f"ua-payment-entry-{digest}"


def _draft_payment_entries(invoice_name: str) -> list[str]:
	references = frappe.get_all(
		"Payment Entry Reference",
		filters={
			"reference_doctype": "Purchase Invoice",
			"reference_name": invoice_name,
		},
		pluck="parent",
	)
	if not references:
		return []

	return frappe.get_all(
		"Payment Entry",
		filters={"name": ("in", list(dict.fromkeys(references))), "docstatus": 0},
		order_by="creation asc",
		pluck="name",
	)


def _validate_invoice(invoice_name: str):
	invoice = frappe.get_doc("Purchase Invoice", invoice_name)
	invoice.check_permission("read")
	if invoice.docstatus != 1:
		frappe.throw(_("Рахунок постачальника {0} має бути проведений").format(invoice.name))
	if invoice.status in ("On Hold", "Closed") or invoice.invoice_is_blocked():
		frappe.throw(_("Рахунок постачальника {0} заблокований для оплати").format(invoice.name))
	if not flt(invoice.outstanding_amount):
		frappe.throw(_("Рахунок постачальника {0} не має суми до оплати").format(invoice.name))
	return invoice


def _insert_payment_entry(invoice_name: str) -> str:
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	payment = get_payment_entry("Purchase Invoice", invoice_name)
	payment.flags.ignore_validate = True
	payment.set_title_field()
	payment.insert(ignore_mandatory=True)
	frappe.db.commit()
	return payment.name


def _get_or_create_draft(invoice_name: str) -> dict:
	invoice = _validate_invoice(invoice_name)
	with filelock(_lock_name(invoice.name), timeout=10):
		existing = _draft_payment_entries(invoice.name)
		if existing:
			return {
				"invoice_name": invoice.name,
				"name": existing[0],
				"existing": True,
				"duplicate_names": existing[1:],
			}

		frappe.flags.bulk_transaction = True
		try:
			payment_name = _insert_payment_entry(invoice.name)
		finally:
			frappe.flags.bulk_transaction = False

	return {
		"invoice_name": invoice.name,
		"name": payment_name,
		"existing": False,
		"duplicate_names": [],
	}


@frappe.whitelist(methods=["POST"])
def create_payment_entries(invoice_names: str | list[str]) -> dict:
	"""Create one draft immediately or enqueue a batch and return navigation metadata."""
	frappe.has_permission("Purchase Invoice", "read", throw=True)
	frappe.has_permission("Payment Entry", "create", throw=True)
	frappe.has_permission("Payment Entry", "read", throw=True)
	names = _normalize_invoice_names(invoice_names)

	if len(names) == 1:
		return {
			"mode": "single",
			"created": [_get_or_create_draft(names[0])],
			"failed": [],
		}

	requested_by = frappe.session.user
	job_id = _job_id(names, requested_by)
	job = frappe.enqueue(
		create_payment_entries_job,
		queue="default",
		timeout=300,
		job_id=job_id,
		deduplicate=True,
		invoice_names=names,
		requested_by=requested_by,
		result_job_id=job_id,
	)
	return {
		"mode": "background",
		"job_id": job_id,
		"count": len(names),
		"already_running": job is None,
	}


def create_payment_entries_job(
	invoice_names: list[str],
	requested_by: str,
	result_job_id: str,
) -> None:
	"""Create draft payments independently and notify the requesting Desk user."""
	created = []
	failed = []
	for index, invoice_name in enumerate(invoice_names):
		savepoint = f"ua_payment_entry_{index}"
		frappe.db.savepoint(savepoint)
		try:
			created.append(_get_or_create_draft(invoice_name))
		except Exception as exc:
			frappe.db.rollback(save_point=savepoint)
			failed.append({"invoice_name": invoice_name, "error": str(exc)})
			frappe.log_error(
				title=f"Payment Entry draft failed: {invoice_name}",
				message=frappe.get_traceback(with_context=True),
			)

	frappe.db.commit()
	frappe.publish_realtime(
		COMPLETION_EVENT,
		{
			"job_id": result_job_id,
			"created": created,
			"failed": failed,
		},
		room=get_user_room(requested_by),
	)

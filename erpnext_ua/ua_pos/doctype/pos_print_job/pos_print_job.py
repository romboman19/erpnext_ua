import base64

import frappe
from frappe.model.document import Document


class POSPrintJob(Document):
	def validate(self):
		if self.is_new():
			self.requested_by = self.requested_by or frappe.session.user
			if not self.payload_base64:
				frappe.throw("Print Job не має зафіксованого payload")
			try:
				payload = base64.b64decode(self.payload_base64, validate=True)
			except ValueError:
				frappe.throw("Print Job містить некоректний base64 payload")
			if not payload or len(payload) > 128 * 1024:
				frappe.throw("Payload друку порожній або перевищує 128 KiB")
		elif self.has_value_changed("payload_base64") or self.has_value_changed("idem_key"):
			frappe.throw("Payload та idempotency key завдання друку є незмінними")

	def on_trash(self):
		frappe.throw("Журнал друку є незмінним і не може бути видалений")

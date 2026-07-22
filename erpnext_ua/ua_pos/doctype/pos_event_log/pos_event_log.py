import frappe
from frappe.model.document import Document


class POSEventLog(Document):
	def on_trash(self):
		frappe.throw("POS event log is append-only")


import frappe
from frappe.model.document import Document


class TerminalTransaction(Document):
	def on_trash(self):
		frappe.throw("Terminal transactions are append-only")


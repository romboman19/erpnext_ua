import frappe
from frappe.model.document import Document


class POSCashMovement(Document):
	def before_cancel(self):
		frappe.throw("Cash movements are append-only; create a reversal movement")

	def on_trash(self):
		frappe.throw("Cash movements cannot be deleted")


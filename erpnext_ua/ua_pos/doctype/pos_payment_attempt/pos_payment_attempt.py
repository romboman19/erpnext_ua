import frappe
from frappe.model.document import Document


class POSPaymentAttempt(Document):
	def before_cancel(self):
		frappe.throw("Payment attempts are immutable; reverse the confirmed operation")


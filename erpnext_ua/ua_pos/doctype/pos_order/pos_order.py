import frappe
from frappe.model.document import Document


FINAL_STATES = {"Completed", "Completed Print Error", "Cancelled"}


class POSOrder(Document):
	def validate(self):
		self.net_total = 0
		self.discount_total = 0
		for row in self.items or []:
			gross = (row.qty or 0) * (row.rate or 0)
			row.amount = gross - (row.discount_amount or 0)
			self.net_total += row.amount
			self.discount_total += row.discount_amount or 0
		self.grand_total = self.net_total
		self.paid_total = sum((row.amount or 0) for row in self.payments_plan or [] if row.status == "Confirmed")

	def on_trash(self):
		if self.status in FINAL_STATES:
			frappe.throw("Final POS orders cannot be deleted")


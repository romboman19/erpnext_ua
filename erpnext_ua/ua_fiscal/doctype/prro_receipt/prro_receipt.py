import frappe
from frappe.model.document import Document


class PRROReceipt(Document):
	def validate(self):
		if self.receipt_kind == "Return" and not self.related_receipt:
			frappe.throw("Для фіскального чека повернення обовʼязково вкажіть первинний чек")

	def on_trash(self):
		if self.status not in {"Draft", "Cancelled"}:
			frappe.throw("Фіскальний журнал є незмінним; доставлені, офлайн або невизначені документи видаляти не можна")

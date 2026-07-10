import frappe
from frappe.model.document import Document


class UATaxDeadline(Document):
	def validate(self):
		if not self.fop_profile:
			self.fop_profile = frappe.db.get_value("FOP Profile", {"company": self.company})

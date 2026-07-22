import frappe
from frappe.model.document import Document


class POSCashDesk(Document):
	def validate(self):
		warehouse_company = frappe.db.get_value("Warehouse", self.warehouse, "company")
		if warehouse_company and warehouse_company != self.company:
			frappe.throw("Warehouse must belong to the cash desk company")


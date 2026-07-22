from frappe.model.document import Document


class POSOperationalShift(Document):
	def validate(self):
		for row in [*(self.opening_counts or []), *(self.closing_counts or [])]:
			row.subtotal = (row.denomination or 0) * (row.qty or 0)


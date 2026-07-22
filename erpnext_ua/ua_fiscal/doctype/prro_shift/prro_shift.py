import frappe
from frappe.model.document import Document


class PRROShift(Document):
	def validate(self):
		if self.cash_register and not self.fop_profile:
			self.fop_profile = frappe.db.get_value("PRRO Cash Register", self.cash_register, "fop_profile")
		if self.status in ("Opening", "Open"):
			other_open = frappe.db.exists(
				"PRRO Shift",
				{
					"cash_register": self.cash_register,
					"status": ("in", ("Opening", "Open", "Closing")),
					"name": ("!=", self.name),
				},
			)
			if other_open:
				frappe.throw(f"На касі вже є незакрита зміна: {other_open}")

	def on_trash(self):
		if self.status != "Opening" or frappe.db.exists("PRRO Receipt", {"shift": self.name}):
			frappe.throw("Фіскальну зміну з документами видаляти не можна")

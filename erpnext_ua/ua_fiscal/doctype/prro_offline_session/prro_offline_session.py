import frappe
from frappe.model.document import Document


class PRROOfflineSession(Document):
	def validate(self):
		self.session_key = f"{self.cash_register}:{self.session_id}"
		if self.status in {"Opening", "Open", "Closing", "Queued", "Sending"}:
			other = frappe.db.exists(
				"PRRO Offline Session",
				{
					"cash_register": self.cash_register,
					"status": ("in", ("Opening", "Open", "Closing", "Queued", "Sending")),
					"name": ("!=", self.name),
				},
			)
			if other:
				frappe.throw(f"На касі вже є незавершена офлайн-сесія: {other}")

	def on_trash(self):
		if frappe.db.exists("PRRO Receipt", {"offline_session": self.name}):
			frappe.throw("Офлайн-сесію з фіскальними документами видаляти не можна")

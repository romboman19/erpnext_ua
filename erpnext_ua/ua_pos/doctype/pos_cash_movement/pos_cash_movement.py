import frappe
from frappe import _
from frappe.model.document import Document


ACCOUNTED_MOVEMENT_TYPES = {
	"Cash In",
	"Incassation Out",
	"Incassation In",
	"Expense",
	"Transfer Out",
	"Transfer In",
	"Correction",
}


class POSCashMovement(Document):
	def validate(self):
		if frappe.utils.flt(self.amount) <= 0:
			frappe.throw(_("Сума касового руху має бути більшою за нуль"))

	def before_submit(self):
		if self.movement_type not in ACCOUNTED_MOVEMENT_TYPES:
			return
		if not self.counterparty_account or not self.journal_entry:
			frappe.throw(_("Для касового руху {0} потрібна бухгалтерська проводка").format(self.movement_type))
		if frappe.db.get_value("Journal Entry", self.journal_entry, "docstatus") != 1:
			frappe.throw(_("Бухгалтерська проводка {0} не проведена").format(self.journal_entry))

	def before_cancel(self):
		frappe.throw("Cash movements are append-only; create a reversal movement")

	def on_trash(self):
		frappe.throw("Cash movements cannot be deleted")

import frappe
from frappe import _
from frappe.model.document import Document


class POSCashDesk(Document):
	def validate(self):
		self._set_profile_dimensions()
		self._validate_account(self.cash_account, account_types={"Cash"}, label=_("Рахунок готівки каси"))
		self._validate_account(
			self.cash_transfer_account,
			account_types={"Cash", "Bank"},
			label=_("Транзитний рахунок інкасації"),
		)
		if self.cash_account == self.cash_transfer_account:
			frappe.throw(_("Рахунок готівки каси та транзитний рахунок інкасації мають відрізнятися"))
		if self.cash_difference_account:
			self._validate_account(
				self.cash_difference_account,
				root_types={"Expense", "Income"},
				label=_("Рахунок нестач і надлишків"),
			)

	def _set_profile_dimensions(self):
		profile = frappe.db.get_value(
			"POS Profile",
			self.pos_profile,
			["company", "warehouse", "disabled", "update_stock"],
			as_dict=True,
		)
		if not profile:
			frappe.throw(_("POS Profile {0} не знайдено").format(self.pos_profile))
		if profile.disabled:
			frappe.throw(_("POS Profile {0} вимкнено").format(self.pos_profile))
		if not profile.warehouse:
			frappe.throw(_("У POS Profile {0} не задано склад").format(self.pos_profile))
		if not profile.update_stock:
			frappe.throw(_("У POS Profile {0} потрібно увімкнути оновлення складу").format(self.pos_profile))
		self.company = profile.company
		self.warehouse = profile.warehouse

	def _validate_account(self, account, *, account_types=None, root_types=None, label):
		details = frappe.db.get_value(
			"Account",
			account,
			["company", "account_type", "root_type", "account_currency", "is_group", "disabled"],
			as_dict=True,
		)
		if not details:
			frappe.throw(_("{0}: рахунок не знайдено").format(label))
		if details.company != self.company:
			frappe.throw(_("{0} має належати компанії {1}").format(label, self.company))
		if details.is_group or details.disabled:
			frappe.throw(_("{0} має бути активним рахунком, а не групою").format(label))
		company_currency = frappe.get_cached_value("Company", self.company, "default_currency")
		if details.account_currency != company_currency:
			frappe.throw(_("{0} має бути у валюті компанії {1}").format(label, company_currency))
		if account_types and details.account_type not in account_types:
			frappe.throw(_("{0} має бути рахунком типу {1}").format(label, " / ".join(sorted(account_types))))
		if root_types and details.root_type not in root_types:
			frappe.throw(_("{0} має належати до доходів або витрат").format(label))

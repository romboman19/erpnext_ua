"""Контроль доходу ФОП проти ліміту групи ЄП.

Дохід рахуємо касовим методом (як для ЄП): фактичні надходження грошей —
Payment Entry (Receive від Customer) + оплати в POS-рахунках (is_pos), які
не створюють окремих Payment Entry. Повернення коштів (Pay від Customer)
зменшують дохід. Це операційна оцінка, не заміна книги обліку доходів.
"""

from datetime import date

import frappe

ALERT_THRESHOLDS = (80, 95, 100)


def get_year_income(company: str, year: int) -> dict:
	start, end = date(year, 1, 1), date(year, 12, 31)

	received = frappe.db.get_value(
		"Payment Entry",
		{
			"company": company,
			"payment_type": "Receive",
			"party_type": "Customer",
			"docstatus": 1,
			"posting_date": ("between", (start, end)),
		},
		"sum(base_received_amount)",
	) or 0

	refunded = frappe.db.get_value(
		"Payment Entry",
		{
			"company": company,
			"payment_type": "Pay",
			"party_type": "Customer",
			"docstatus": 1,
			"posting_date": ("between", (start, end)),
		},
		"sum(base_paid_amount)",
	) or 0

	pos_paid = frappe.db.get_value(
		"Sales Invoice",
		{
			"company": company,
			"is_pos": 1,
			"docstatus": 1,
			"posting_date": ("between", (start, end)),
		},
		"sum(base_paid_amount)",
	) or 0

	return {
		"received": received,
		"refunded": refunded,
		"pos_paid": pos_paid,
		"income": received + pos_paid - refunded,
	}


@frappe.whitelist()
def get_income_summary(fop_profile: str, year: int | None = None) -> dict:
	year = int(year) if year else frappe.utils.getdate().year
	fop = frappe.get_doc("FOP Profile", fop_profile)
	fop.check_permission("read")

	data = get_year_income(fop.company, year)
	params_name = frappe.db.exists(
		"UA Tax Parameters", {"year": year, "single_tax_group": fop.single_tax_group}
	)
	limit = frappe.db.get_value("UA Tax Parameters", params_name, "income_limit") if params_name else None

	data.update({
		"year": year,
		"company": fop.company,
		"single_tax_group": fop.single_tax_group,
		"income_limit": limit,
		"limit_used_percent": round(data["income"] / limit * 100, 2) if limit else None,
	})
	return data


def check_income_limits():
	"""Scheduler (щодня): алерти при перетині 80/95/100% ліміту, по одному на поріг за рік."""
	year = frappe.utils.getdate().year
	for fop in frappe.get_all(
		"FOP Profile",
		filters={"status": "Active"},
		fields=["name", "company", "single_tax_group", "limit_alert_year", "limit_alert_level"],
	):
		summary = get_income_summary(fop.name, year)
		pct = summary["limit_used_percent"]
		if pct is None:
			continue

		last_level = fop.limit_alert_level if fop.limit_alert_year == year else 0
		crossed = max((t for t in ALERT_THRESHOLDS if pct >= t), default=0)
		if crossed <= last_level:
			continue

		from erpnext_ua.ua_fop.tax_calendar import _accounts_users

		subject = (
			f"{'ПЕРЕВИЩЕНО ЛІМІТ' if crossed >= 100 else f'Використано {pct}% ліміту'} "
			f"доходу групи {fop.single_tax_group}: {fop.company} — "
			f"{frappe.utils.fmt_money(summary['income'], currency='UAH')} із "
			f"{frappe.utils.fmt_money(summary['income_limit'], currency='UAH')} за {year} рік"
		)
		for user in _accounts_users():
			frappe.get_doc({
				"doctype": "Notification Log",
				"for_user": user,
				"type": "Alert",
				"document_type": "FOP Profile",
				"document_name": fop.name,
				"subject": subject,
			}).insert(ignore_permissions=True)

		frappe.db.set_value(
			"FOP Profile", fop.name,
			{"limit_alert_year": year, "limit_alert_level": crossed},
			update_modified=False,
		)
	frappe.db.commit()

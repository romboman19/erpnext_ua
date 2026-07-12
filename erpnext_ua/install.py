import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

# Довідкові параметри 2026 (МЗП 8647 грн, ПМ для працездатних 3028 грн)
TAX_PARAMETERS = [
	{
		"year": 2026,
		"single_tax_group": "1",
		"minimum_wage": 8647,
		"income_limit": 1_444_049,
		"single_tax_monthly": 302.80,
		"military_levy_monthly": 864.70,
		"esv_monthly": 1902.34,
	},
	{
		"year": 2026,
		"single_tax_group": "2",
		"minimum_wage": 8647,
		"income_limit": 7_211_598,
		"single_tax_monthly": 1729.40,
		"military_levy_monthly": 864.70,
		"esv_monthly": 1902.34,
	},
	{
		"year": 2026,
		"single_tax_group": "3",
		"minimum_wage": 8647,
		"income_limit": 10_091_049,
		"single_tax_percent_no_vat": 5,
		"single_tax_percent_vat": 3,
		"military_levy_percent": 1,
		"esv_monthly": 1902.34,
	},
]


def ensure_tax_parameters():
	"""Створює довідкові UA Tax Parameters, якщо їх ще немає (існуючі не перезаписує)."""
	for row in TAX_PARAMETERS:
		if frappe.db.exists(
			"UA Tax Parameters",
			{"year": row["year"], "single_tax_group": row["single_tax_group"]},
		):
			continue
		doc = frappe.new_doc("UA Tax Parameters")
		doc.update(row)
		doc.insert(ignore_permissions=True)
	frappe.db.commit()


POS_ROLES = ["POS Cashier", "POS Senior Cashier", "POS Manager", "POS Administrator", "PRRO Operator"]


def ensure_pos_setup():
	"""Ідемпотентно створює ролі та поля інтеграції POS без змін ERPNext core."""
	for role in POS_ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role}).insert(ignore_permissions=True)

	create_custom_fields(
		{
			"Employee": [
				{"fieldname": "ua_pos_barcode_hash", "label": "POS Barcode Hash", "fieldtype": "Data", "unique": 1},
				{"fieldname": "ua_pos_pin_hash", "label": "POS PIN Hash", "fieldtype": "Password"},
			],
			"Sales Invoice": [
				{"fieldname": "ua_pos_order", "label": "POS Order", "fieldtype": "Link", "options": "POS Order"},
				{"fieldname": "ua_pos_desk", "label": "POS Cash Desk", "fieldtype": "Link", "options": "POS Cash Desk"},
				{"fieldname": "ua_pos_shift", "label": "POS Operational Shift", "fieldtype": "Link", "options": "POS Operational Shift"},
				{"fieldname": "ua_fop_profile", "label": "FOP Profile", "fieldtype": "Link", "options": "FOP Profile"},
			],
			"Mode of Payment": [
				{"fieldname": "ua_pos_kind", "label": "UA POS Kind", "fieldtype": "Select", "options": "\nCash\nCard\nIBAN\nBonus\nInstallment"},
				{"fieldname": "ua_payformcd", "label": "PRRO Payment Form Code", "fieldtype": "Int"},
				{"fieldname": "ua_currency", "label": "POS Currency", "fieldtype": "Link", "options": "Currency", "default": "UAH"},
			],
			"Item": [
				{"fieldname": "ua_serial_mode", "label": "UA Serial Mode", "fieldtype": "Select", "options": "\nStrict\nAdvisory\nNone"},
				{"fieldname": "ua_warranty_months", "label": "Warranty (months)", "fieldtype": "Int"},
			],
			"Customer": [
				{"fieldname": "ua_pos_details_section", "label": "UA POS Customer Details", "fieldtype": "Section Break"},
				{"fieldname": "ua_last_name", "label": "Прізвище", "fieldtype": "Data"},
				{"fieldname": "ua_first_name", "label": "Ім’я", "fieldtype": "Data"},
				{"fieldname": "ua_middle_name", "label": "По батькові", "fieldtype": "Data"},
				{"fieldname": "ua_gender", "label": "Стать", "fieldtype": "Link", "options": "Gender"},
				{"fieldname": "ua_date_of_birth", "label": "Дата народження", "fieldtype": "Date"},
				{"fieldname": "ua_city", "label": "Місто", "fieldtype": "Data"},
				{"fieldname": "ua_pos_comment", "label": "Коментар касира", "fieldtype": "Small Text"},
				{"fieldname": "ua_telegram_chat_id", "label": "Telegram Chat ID", "fieldtype": "Data", "hidden": 1, "read_only": 1},
			],
		},
		update=True,
	)
	frappe.db.commit()

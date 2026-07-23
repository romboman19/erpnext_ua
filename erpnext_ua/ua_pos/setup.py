from __future__ import annotations

import re
import unicodedata

import frappe


def backfill_cash_desk_bridge() -> None:
	"""Link legacy UA POS desks to native profiles, accounts, and employee access."""
	required_tables = (
		"POS Cash Desk",
		"POS Profile",
		"Account",
		"Employee Cash Desk Access",
	)
	if not all(frappe.db.table_exists(doctype) for doctype in required_tables):
		return
	required_columns = ("pos_profile", "cash_account", "cash_transfer_account")
	if not all(frappe.db.has_column("POS Cash Desk", fieldname) for fieldname in required_columns):
		return

	profiles = frappe.get_all(
		"POS Profile",
		filters={"disabled": 0},
		fields=["name", "company", "warehouse"],
		limit_page_length=500,
	)
	for desk in frappe.get_all(
		"POS Cash Desk",
		fields=[
			"name",
			"desk_name",
			"company",
			"warehouse",
			"pos_profile",
			"cash_account",
			"cash_transfer_account",
		],
		limit_page_length=500,
	):
		profile = _resolve_profile(desk, profiles)
		updates = {}
		if profile:
			updates.update(
				{
					"pos_profile": profile.name,
					"company": profile.company,
					"warehouse": profile.warehouse,
				}
			)
		company = profile.company if profile else desk.company
		if company and not desk.cash_account:
			cash_account = _resolve_cash_account(desk, profile, company)
			if cash_account:
				updates["cash_account"] = cash_account
		if company and not desk.cash_transfer_account:
			transfer_account = _resolve_transfer_account(company)
			if transfer_account:
				updates["cash_transfer_account"] = transfer_account
		if updates:
			frappe.db.set_value("POS Cash Desk", desk.name, updates, update_modified=False)
		if profile:
			_backfill_employee_access(desk.name, profile.name)


def _resolve_profile(desk, profiles):
	if desk.pos_profile:
		return next((row for row in profiles if row.name == desk.pos_profile), None)
	desk_keys = {_key(desk.name), _key(desk.desk_name)}
	by_name = [row for row in profiles if _key(row.name) in desk_keys]
	if len(by_name) == 1:
		return by_name[0]
	by_location = [
		row
		for row in profiles
		if row.company == desk.company and row.warehouse == desk.warehouse
	]
	return by_location[0] if len(by_location) == 1 else None


def _resolve_cash_account(desk, profile, company: str) -> str | None:
	accounts = frappe.get_all(
		"Account",
		filters={
			"company": company,
			"account_type": "Cash",
			"is_group": 0,
			"disabled": 0,
		},
		fields=["name", "account_name"],
		limit_page_length=500,
	)
	keys = {_key(desk.name), _key(desk.desk_name)}
	if profile:
		keys.add(_key(profile.name))
	exact = [row.name for row in accounts if _key(row.account_name) in keys or _key(row.name) in keys]
	if len(exact) == 1:
		return exact[0]
	numbers = set(re.findall(r"\d+", " ".join(filter(None, (desk.name, desk.desk_name)))))
	if profile:
		numbers.update(re.findall(r"\d+", profile.name))
	numbered = [
		row.name
		for row in accounts
		if "каса" in _key(row.account_name)
		and numbers.intersection(re.findall(r"\d+", row.account_name or ""))
	]
	return numbered[0] if len(numbered) == 1 else None


def _resolve_transfer_account(company: str) -> str | None:
	accounts = frappe.get_all(
		"Account",
		filters={
			"company": company,
			"account_type": ("in", ("Cash", "Bank")),
			"is_group": 0,
			"disabled": 0,
		},
		fields=["name", "account_name"],
		limit_page_length=500,
	)
	matches = [row.name for row in accounts if "інкасац" in _key(row.account_name)]
	return matches[0] if len(matches) == 1 else None


def _backfill_employee_access(cash_desk: str, pos_profile: str) -> None:
	profile = frappe.get_cached_doc("POS Profile", pos_profile)
	for profile_user in profile.applicable_for_users:
		employee = frappe.db.get_value(
			"Employee",
			{"user_id": profile_user.user, "status": "Active"},
			"name",
		)
		if not employee or frappe.db.exists(
			"Employee Cash Desk Access",
			{"employee": employee, "cash_desk": cash_desk},
		):
			continue
		frappe.get_doc(
			{
				"doctype": "Employee Cash Desk Access",
				"employee": employee,
				"cash_desk": cash_desk,
				"access_role": "Cashier",
				"active": 1,
			}
		).insert(ignore_permissions=True)


def _key(value: str | None) -> str:
	normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
	return "".join(character for character in normalized if character.isalnum())

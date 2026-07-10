"""Генерація податкового календаря ФОП.

Строки (ПКУ, станом на 2026):
- ЄП гр. 1-2: авансовий платіж щомісяця, не пізніше 20 числа поточного місяця.
- ВЗ гр. 1-2: щомісяця, разом з ЄП (10% МЗП).
- ЄП + ВЗ гр. 3: протягом 10 к.д. після граничного строку квартальної декларації
  (40 к.д. після кварталу), тобто 50 к.д. після кінця кварталу.
- ЄСВ «за себе»: щокварталу, до 20 числа місяця, наступного за кварталом.
- Декларація гр. 1-2: річна, протягом 60 к.д. після завершення року.
- Декларація гр. 3: квартальна, протягом 40 к.д. після кварталу.

Якщо граничний строк сплати припадає на вихідний — сплатити треба напередодні,
тому дати не переносяться вперед (це відповідальність користувача; у примітці
дедлайну це зазначено).
"""

from datetime import date, timedelta

import frappe

QUARTERS = {1: (1, 3), 2: (4, 6), 3: (7, 9), 4: (10, 12)}
MONTH_NAMES = [
	"січень", "лютий", "березень", "квітень", "травень", "червень",
	"липень", "серпень", "вересень", "жовтень", "листопад", "грудень",
]


def _quarter_end(year: int, q: int) -> date:
	last_month = QUARTERS[q][1]
	next_month_first = date(year + (1 if last_month == 12 else 0), (last_month % 12) + 1, 1)
	return next_month_first - timedelta(days=1)


def _get_params(year: int, group: str):
	name = frappe.db.exists("UA Tax Parameters", {"year": year, "single_tax_group": group})
	return frappe.get_doc("UA Tax Parameters", name) if name else None


def _rows_for_group(year: int, group: str) -> list[dict]:
	params = _get_params(year, group)
	rows = []

	if group in ("1", "2"):
		for m in range(1, 13):
			label = f"{MONTH_NAMES[m - 1]} {year}"
			rows.append({
				"tax_type": "Єдиний податок",
				"period_label": label,
				"due_date": date(year, m, 20),
				"amount": params.single_tax_monthly if params else None,
				"notes": "Авансовий платіж ЄП. Якщо 20-те — вихідний, сплатіть напередодні.",
			})
			rows.append({
				"tax_type": "Військовий збір",
				"period_label": label,
				"due_date": date(year, m, 20),
				"amount": params.military_levy_monthly if params else None,
				"notes": "ВЗ разом з авансом ЄП.",
			})
		rows.append({
			"tax_type": "Декларація ЄП",
			"period_label": f"{year} рік",
			"due_date": date(year, 12, 31) + timedelta(days=60),
			"notes": "Річна декларація платника ЄП (60 к.д. після року).",
		})
	else:  # група 3
		for q in range(1, 5):
			q_end = _quarter_end(year, q)
			label = f"{q} квартал {year}"
			rows.append({
				"tax_type": "Декларація ЄП",
				"period_label": label,
				"due_date": q_end + timedelta(days=40),
				"notes": "Квартальна декларація платника ЄП (40 к.д. після кварталу).",
			})
			rows.append({
				"tax_type": "Єдиний податок",
				"period_label": label,
				"due_date": q_end + timedelta(days=50),
				"notes": "ЄП за квартал (% доходу), 10 к.д. після строку декларації.",
			})
			rows.append({
				"tax_type": "Військовий збір",
				"period_label": label,
				"due_date": q_end + timedelta(days=50),
				"notes": "ВЗ 1% доходу, разом з ЄП.",
			})

	# ЄСВ — однаково для всіх груп: до 20 числа після кварталу
	esv_quarter_amount = params.esv_monthly * 3 if params and params.esv_monthly else None
	for q in range(1, 5):
		q_end = _quarter_end(year, q)
		due = date(q_end.year + (1 if q == 4 else 0), (q_end.month % 12) + 1, 20)
		rows.append({
			"tax_type": "ЄСВ",
			"period_label": f"{q} квартал {year}",
			"due_date": due,
			"amount": esv_quarter_amount,
			"notes": "ЄСВ «за себе» за квартал (мінімум за 3 місяці).",
		})
	return rows


@frappe.whitelist()
def generate_deadlines(fop_profile: str, year: int | None = None) -> dict:
	"""Створює дедлайни для ФОП на рік. Існуючі записи не дублює."""
	year = int(year) if year else frappe.utils.getdate().year
	fop = frappe.get_doc("FOP Profile", fop_profile)
	created = skipped = 0
	for row in _rows_for_group(year, fop.single_tax_group):
		exists = frappe.db.exists(
			"UA Tax Deadline",
			{"company": fop.company, "tax_type": row["tax_type"], "due_date": row["due_date"]},
		)
		if exists:
			skipped += 1
			continue
		doc = frappe.new_doc("UA Tax Deadline")
		doc.update(row)
		doc.company = fop.company
		doc.fop_profile = fop.name
		doc.insert(ignore_permissions=True)
		created += 1
	frappe.db.commit()
	return {"created": created, "skipped": skipped, "year": year}


def generate_for_all_fops():
	"""Scheduler (щомісяця): гарантує календар на поточний і наступний рік для активних ФОП."""
	year = frappe.utils.getdate().year
	for name in frappe.get_all("FOP Profile", filters={"status": "Active"}, pluck="name"):
		generate_deadlines(name, year)
		if frappe.utils.getdate().month == 12:
			generate_deadlines(name, year + 1)


def update_statuses_and_notify():
	"""Scheduler (щодня): оновлює статуси дедлайнів і надсилає нагадування."""
	today = frappe.utils.getdate()
	soon = today + timedelta(days=3)
	open_deadlines = frappe.get_all(
		"UA Tax Deadline",
		filters={"status": ("!=", "Виконано")},
		fields=["name", "company", "tax_type", "period_label", "due_date", "status",
				"notified_due_soon", "notified_overdue"],
	)
	for d in open_deadlines:
		due = frappe.utils.getdate(d.due_date)
		if due < today:
			new_status = "Прострочено"
		elif due <= soon:
			new_status = "Скоро термін"
		else:
			new_status = "Заплановано"
		if new_status != d.status:
			frappe.db.set_value("UA Tax Deadline", d.name, "status", new_status, update_modified=False)

		if new_status == "Скоро термін" and not d.notified_due_soon:
			_notify(d, f"До {frappe.utils.formatdate(due, 'dd.MM.yyyy')} — {d.tax_type} ({d.period_label}), {d.company}")
			frappe.db.set_value("UA Tax Deadline", d.name, "notified_due_soon", 1, update_modified=False)
		elif new_status == "Прострочено" and not d.notified_overdue:
			_notify(d, f"ПРОСТРОЧЕНО: {d.tax_type} ({d.period_label}), {d.company} — строк був {frappe.utils.formatdate(due, 'dd.MM.yyyy')}")
			frappe.db.set_value("UA Tax Deadline", d.name, "notified_overdue", 1, update_modified=False)
	frappe.db.commit()


def _accounts_users() -> list[str]:
	users = frappe.get_all(
		"Has Role",
		filters={"role": ("in", ["Accounts Manager", "System Manager"]), "parenttype": "User"},
		pluck="parent",
	)
	return [
		u for u in set(users)
		if u not in ("Administrator", "Guest")
		and frappe.db.get_value("User", u, "enabled")
	] or ["Administrator"]


def _notify(deadline, subject: str):
	for user in _accounts_users():
		frappe.get_doc({
			"doctype": "Notification Log",
			"for_user": user,
			"type": "Alert",
			"document_type": "UA Tax Deadline",
			"document_name": deadline.name,
			"subject": subject,
		}).insert(ignore_permissions=True)

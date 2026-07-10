app_name = "erpnext_ua"
app_title = "ERPNext Ukraine"
app_publisher = "HUNTER.rv"
app_description = "Ukrainian localization for ERPNext: FOP profiles, tax parameters, print formats, translations"
app_email = "it@hunter.rv.ua"
app_license = "MIT"
required_apps = ["erpnext"]

after_install = "erpnext_ua.install.ensure_tax_parameters"

after_migrate = [
    "erpnext_ua.install.ensure_tax_parameters",
]

scheduler_events = {
    "daily": [
        "erpnext_ua.ua_fop.tax_calendar.update_statuses_and_notify",
        "erpnext_ua.ua_fop.income_monitor.check_income_limits",
    ],
    "monthly": [
        "erpnext_ua.ua_fop.tax_calendar.generate_for_all_fops",
    ],
}

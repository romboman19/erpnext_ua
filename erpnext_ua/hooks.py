app_name = "erpnext_ua"
app_title = "ERPNext Ukraine"
app_publisher = "HUNTER.rv"
app_description = "Ukraine business layer for ERPNext: FOP, cash desk/POS, PRRO, tax controls and documents"
app_email = "it@hunter.rv.ua"
app_license = "MIT"
required_apps = ["erpnext"]

after_install = [
    "erpnext_ua.install.ensure_tax_parameters",
    "erpnext_ua.install.ensure_pos_setup",
]

after_migrate = [
    "erpnext_ua.install.ensure_tax_parameters",
    "erpnext_ua.install.ensure_pos_setup",
]

doctype_js = {
    "Sales Invoice": "ua_fiscal/doctype_js/sales_invoice_fiscal.js",
    "PB POS Terminal": "ua_pos/public/js/pb_pos_terminal.js",
}

doc_events = {
    "Sales Invoice": {
        "on_submit": "erpnext_ua.ua_fiscal.sales_invoice.on_submit",
    },
}

scheduler_events = {
    "daily": [
        "erpnext_ua.ua_fop.tax_calendar.update_statuses_and_notify",
        "erpnext_ua.ua_fop.income_monitor.check_income_limits",
    ],
    "monthly": [
        "erpnext_ua.ua_fop.tax_calendar.generate_for_all_fops",
    ],
}

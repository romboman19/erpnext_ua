frappe.ui.form.on("FOP Profile", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("Згенерувати податковий календар"), () => {
			frappe.prompt(
				{
					fieldname: "year",
					fieldtype: "Int",
					label: __("Рік"),
					default: new Date().getFullYear(),
					reqd: 1,
				},
				(values) => {
					frappe
						.call("erpnext_ua.ua_fop.tax_calendar.generate_deadlines", {
							fop_profile: frm.doc.name,
							year: values.year,
						})
						.then((r) => {
							const m = r.message;
							frappe.msgprint(
								__("Календар на {0}: створено {1}, вже існувало {2}", [
									m.year,
									m.created,
									m.skipped,
								])
							);
						});
				},
				__("Податковий календар")
			);
		});

		frm.add_custom_button(__("Дедлайни"), () => {
			frappe.set_route("List", "UA Tax Deadline", { company: frm.doc.company });
		});

		render_headline(frm);
	},
});

function render_headline(frm) {
	const fmt = (v) => format_currency(v, "UAH");
	Promise.all([
		frm.call("get_current_tax_parameters"),
		frappe.call("erpnext_ua.ua_fop.income_monitor.get_income_summary", {
			fop_profile: frm.doc.name,
		}),
	]).then(([params_r, income_r]) => {
		const parts = [];
		const p = params_r.message;
		const inc = income_r.message;

		if (inc && inc.income_limit) {
			const pct = inc.limit_used_percent;
			const color = pct >= 95 ? "red" : pct >= 80 ? "orange" : "green";
			parts.push(
				`Дохід ${inc.year}: <b style="color:${color}">${fmt(inc.income)}</b> ` +
					`з ${fmt(inc.income_limit)} (<b style="color:${color}">${pct}%</b> ліміту)`
			);
		}
		if (p) {
			if (p.single_tax_monthly) parts.push(`ЄП: <b>${fmt(p.single_tax_monthly)}/міс</b>`);
			if (p.single_tax_percent_no_vat && frm.doc.tax_rate_mode === "5% без ПДВ")
				parts.push(`ЄП: <b>${p.single_tax_percent_no_vat}%</b>`);
			if (p.single_tax_percent_vat && frm.doc.tax_rate_mode === "3% з ПДВ")
				parts.push(`ЄП: <b>${p.single_tax_percent_vat}% + ПДВ</b>`);
			if (p.military_levy_monthly) parts.push(`ВЗ: <b>${fmt(p.military_levy_monthly)}/міс</b>`);
			if (p.military_levy_percent) parts.push(`ВЗ: <b>${p.military_levy_percent}%</b>`);
			if (p.esv_monthly) parts.push(`ЄСВ: <b>${fmt(p.esv_monthly)}/міс</b>`);
		}
		if (parts.length) frm.dashboard.set_headline(parts.join(" · "));
	});
}

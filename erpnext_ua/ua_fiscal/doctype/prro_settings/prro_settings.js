frappe.ui.form.on("PRRO Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Перевірити звʼязок з ДПС"), () => {
			frappe.call("erpnext_ua.ua_fiscal.fiscal_client.check_server_state").then((r) => {
				frappe.msgprint(
					__("Сервер відповів: {0}", [r.message && r.message.Timestamp]),
					__("Звʼязок з фіскальним сервером")
				);
			});
		});
	},
});

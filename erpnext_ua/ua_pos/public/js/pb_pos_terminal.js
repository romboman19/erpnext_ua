frappe.ui.form.on("PB POS Terminal", {
  refresh(frm) {
    if (frm.is_new()) return;
    frm.add_custom_button("Перевірити з’єднання", () => call("test_connection"), "Термінал");
    frm.add_custom_button("Тестова оплата", () => {
      frappe.prompt({ fieldname: "amount", fieldtype: "Currency", label: "Сума", reqd: 1 },
        (v) => call("test_payment", { amount: v.amount }));
    }, "Термінал");
    frm.add_custom_button("Перевірити операцію", () => {
      frappe.prompt({ fieldname: "operation_id", fieldtype: "Data", label: "Ідентифікатор операції", reqd: 1 },
        (v) => call("operation_status", { operation_id: v.operation_id }));
    }, "Термінал");

    function call(method, args = {}) {
      frappe.call({
        method: `erpnext_ua.ua_pos.terminal_service.${method}`,
        args: { terminal: frm.doc.name, ...args },
        freeze: true,
        callback: (r) => frappe.msgprint(`<pre>${frappe.utils.escape_html(JSON.stringify(r.message, null, 2))}</pre>`),
      });
    }
  },
});

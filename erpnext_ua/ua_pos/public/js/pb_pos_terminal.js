frappe.ui.form.on("PB POS Terminal", {
  refresh(frm) {
    if (frm.is_new()) return;
    frm.add_custom_button("Завантажити дані з термінала", async () => {
      if (frm.is_dirty()) {
        frappe.msgprint("Спочатку збережіть IP-адресу та порт термінала.");
        return;
      }
      const response = await frappe.call({
        method: "erpnext_ua.ua_pos.terminal_service.load_terminal_data",
        args: { terminal: frm.doc.name },
        freeze: true,
        freeze_message: "Отримуємо реквізити з термінала…",
      });
      await frm.reload_doc();
      const result = response.message || {};
      const loaded = (result.updated_labels || []).join(", ") || "термінал не повернув фіскальних реквізитів";
      const missing = (result.missing_labels || []).join(", ");
      frappe.msgprint({
        title: "Дані термінала",
        indicator: result.updated?.length ? "green" : "orange",
        message: `Завантажено: ${frappe.utils.escape_html(loaded)}${
          missing ? `<br><br>Не отримано: ${frappe.utils.escape_html(missing)}` : ""
        }`,
      });
    }, "Термінал");
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

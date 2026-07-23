(() => {
	"use strict";

	const COMPLETION_EVENT = "erpnext_ua_payment_entries_created";
	const CREATE_METHOD = "erpnext_ua.ua_payments.service.create_payment_entries";

	frappe.provide("erpnext_ua.payment_entry_navigation");
	const state = erpnext_ua.payment_entry_navigation;
	state.in_flight = state.in_flight || new Set();
	state.active_jobs = state.active_jobs || new Map();
	state.completed_jobs = state.completed_jobs || new Set();

	function payment_link(name) {
		return frappe.utils.get_form_link(
			"Payment Entry",
			name,
			true,
			frappe.utils.escape_html(name)
		);
	}

	function selection_key(names) {
		return [...names].sort().join("|");
	}

	function duplicate_names(created) {
		return created.flatMap((row) => row.duplicate_names || []);
	}

	function show_duplicate_warning(created) {
		const duplicates = duplicate_names(created);
		if (!duplicates.length) {
			return;
		}
		frappe.show_alert(
			{
				message: __("Знайдено дублікати чернеток платежу: {0}", [
					duplicates.map(payment_link).join(", "),
				]),
				indicator: "orange",
			},
			10
		);
	}

	function show_batch_result(result) {
		const created = result.created || [];
		const failed = result.failed || [];
		const created_items = created
			.map(
				(row) =>
					`<li>${payment_link(row.name)} — ${frappe.utils.escape_html(
						row.invoice_name
					)}${row.existing ? ` (${__("вже існував")})` : ""}</li>`
			)
			.join("");
		const failed_items = failed
			.map(
				(row) =>
					`<li>${frappe.utils.escape_html(row.invoice_name)}: ${frappe.utils.escape_html(
						row.error
					)}</li>`
			)
			.join("");

		const sections = [];
		if (created_items) {
			sections.push(`<p>${__("Чернетки платежів:")}</p><ul>${created_items}</ul>`);
		}
		if (failed_items) {
			sections.push(`<p>${__("Не вдалося створити:")}</p><ul>${failed_items}</ul>`);
		}

		frappe.msgprint({
			title: failed.length ? __("Створення платежів завершено частково") : __("Платежі створено"),
			indicator: failed.length ? "orange" : "green",
			message: sections.join(""),
		});
		show_duplicate_warning(created);
		window.cur_list?.refresh();
	}

	function handle_completion(result) {
		const key = state.active_jobs.get(result.job_id);
		if (key) {
			state.active_jobs.delete(result.job_id);
			state.in_flight.delete(key);
		} else {
			state.completed_jobs.add(result.job_id);
		}
		show_batch_result(result);
	}

	if (!state.realtime_registered) {
		frappe.realtime.on(COMPLETION_EVENT, handle_completion);
		state.realtime_registered = true;
	}

	async function create_payment_entries(listview) {
		const selected = listview.get_checked_items();
		if (!selected.length) {
			frappe.msgprint(__("Виберіть хоча б один рахунок постачальника"));
			return;
		}
		if (selected.some((row) => Number(row.docstatus) !== 1)) {
			frappe.msgprint(__("Вибрані рахунки постачальника мають бути проведені"));
			return;
		}

		const names = selected.map((row) => row.name);
		const key = selection_key(names);
		if (state.in_flight.has(key)) {
			frappe.show_alert({
				message: __("Створення платежів для цього вибору вже виконується"),
				indicator: "orange",
			});
			return;
		}

		state.in_flight.add(key);
		const confirmed = await new Promise((resolve) => {
			const message =
				names.length === 1
					? __("Створити чернетку платежу для вибраного рахунку?")
					: __("Створити {0} чернеток платежів?", [names.length]);
			frappe.confirm(message, () => resolve(true), () => resolve(false));
		});
		if (!confirmed) {
			state.in_flight.delete(key);
			return;
		}

		try {
			const response = await frappe.call({
				method: CREATE_METHOD,
				type: "POST",
				args: { invoice_names: names },
				freeze: names.length === 1,
				freeze_message: __("Створюємо чернетку платежу…"),
			});
			const result = response.message;
			if (result.mode === "single") {
				const payment = result.created[0];
				show_duplicate_warning(result.created);
				frappe.set_route("Form", "Payment Entry", payment.name);
				state.in_flight.delete(key);
				return;
			}

			if (state.completed_jobs.has(result.job_id)) {
				state.completed_jobs.delete(result.job_id);
				state.in_flight.delete(key);
			} else {
				state.active_jobs.set(result.job_id, key);
			}
			frappe.show_alert({
				message: result.already_running
					? __("Створення цих платежів уже виконується у фоні")
					: __("Платежі створюються у фоні. Після завершення з’являться посилання."),
				indicator: "blue",
			});
		} catch {
			state.in_flight.delete(key);
		}
	}

	const processor = window.erpnext?.bulk_transaction_processing;
	if (!processor?.create) {
		return;
	}
	if (!processor.create.__erpnext_ua_payment_navigation) {
		const original_create = processor.create;
		const wrapped_create = function (listview, from_doctype, to_doctype, args) {
			if (from_doctype === "Purchase Invoice" && to_doctype === "Payment Entry") {
				return create_payment_entries(listview);
			}
			return original_create.call(this, listview, from_doctype, to_doctype, args);
		};
		wrapped_create.__erpnext_ua_payment_navigation = true;
		processor.create = wrapped_create;
	}
})();

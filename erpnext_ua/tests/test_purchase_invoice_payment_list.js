const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const source = fs.readFileSync(
	"erpnext_ua/public/js/purchase_invoice_payment_list.js",
	"utf8"
);
const calls = [];
const messages = [];
const realtimeHandlers = new Map();
const routes = [];
let responseMessage = {
	mode: "single",
	created: [{ invoice_name: "PINV-1", name: "PAY-1", existing: false, duplicate_names: [] }],
	failed: [],
};

const context = {
	console,
	window: null,
	erpnext: {
		bulk_transaction_processing: {
			create: () => "standard-handler",
		},
	},
	frappe: {
		call: async (options) => {
			calls.push(options);
			return { message: responseMessage };
		},
		confirm: (_message, onYes) => onYes(),
		msgprint: (options) => messages.push(options),
		provide: (path) => {
			let target = context;
			for (const part of path.split(".")) {
				target[part] = target[part] || {};
				target = target[part];
			}
		},
		realtime: {
			on: (event, handler) => realtimeHandlers.set(event, handler),
		},
		set_route: (...route) => routes.push(route),
		show_alert: () => {},
		utils: {
			escape_html: (value) => String(value),
			get_form_link: (_doctype, name, html) =>
				html ? `<a href="/desk/payment-entry/${name}">${name}</a>` : name,
		},
	},
	__: (message, values) =>
		(values || []).reduce(
			(result, value, index) => result.replace(`{${index}}`, value),
			message
		),
};
context.window = context;

vm.runInNewContext(source, context);

async function run() {
	const create = context.erpnext.bulk_transaction_processing.create;
	await create(
		{ get_checked_items: () => [{ name: "PINV-1", docstatus: 1 }] },
		"Purchase Invoice",
		"Payment Entry"
	);
	assert.equal(calls[0].method, "erpnext_ua.ua_payments.service.create_payment_entries");
	assert.deepEqual(routes[0], ["Form", "Payment Entry", "PAY-1"]);

	responseMessage = {
		mode: "background",
		job_id: "job-2",
		count: 2,
		already_running: false,
	};
	await create(
		{
			get_checked_items: () => [
				{ name: "PINV-1", docstatus: 1 },
				{ name: "PINV-2", docstatus: 1 },
			],
		},
		"Purchase Invoice",
		"Payment Entry"
	);
	realtimeHandlers.get("erpnext_ua_payment_entries_created")({
		job_id: "job-2",
		created: [
			{ invoice_name: "PINV-1", name: "PAY-1", existing: false, duplicate_names: [] },
			{ invoice_name: "PINV-2", name: "PAY-2", existing: false, duplicate_names: [] },
		],
		failed: [],
	});
	assert.match(messages.at(-1).message, /PAY-1/);
	assert.match(messages.at(-1).message, /PAY-2/);
	assert.equal(context.erpnext_ua.payment_entry_navigation.in_flight.size, 0);

	assert.equal(create({}, "Sales Invoice", "Payment Entry"), "standard-handler");
	console.log("purchase invoice payment list behavior: OK");
}

run().catch((error) => {
	console.error(error);
	process.exitCode = 1;
});

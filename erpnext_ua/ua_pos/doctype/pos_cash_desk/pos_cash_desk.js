frappe.ui.form.on("POS Cash Desk", {
	setup(frm) {
		const companyFilters = (extra = {}) => ({
			company: frm.doc.company || undefined,
			is_group: 0,
			disabled: 0,
			...extra,
		});

		frm.set_query("cash_account", () => ({
			filters: companyFilters({ account_type: "Cash" }),
		}));
		frm.set_query("cash_transfer_account", () => ({
			filters: companyFilters({ account_type: ["in", ["Cash", "Bank"]] }),
		}));
		frm.set_query("cash_difference_account", () => ({
			filters: companyFilters({ root_type: ["in", ["Expense", "Income"]] }),
		}));
	},
});

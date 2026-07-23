from __future__ import annotations

import json
import unittest
from pathlib import Path

import erpnext_ua.hooks as hooks


APP = Path(__file__).resolve().parents[1]


class TestPOSIntegrationContracts(unittest.TestCase):
    def test_upgrade_creates_module_before_pos_page(self):
        install_source = (APP / "install.py").read_text(encoding="utf-8")
        self.assertIn("def ensure_app_modules():", install_source)
        self.assertIn('"module_name": module_name', install_source)
        self.assertIn('"app_name": "erpnext_ua"', install_source)
        self.assertIn("def ensure_pos_workspace():", install_source)
        self.assertIn('"workspace_sidebar", "ua_pos_workspace.json"', install_source)
        self.assertIn('"desktop_icon", "ua_pos_workspace.json"', install_source)
        self.assertIn("import_file_by_path(path, force=True)", install_source)

        modules_hook = "erpnext_ua.install.ensure_app_modules"
        workspace_hook = "erpnext_ua.install.ensure_pos_workspace"
        page_hook = "erpnext_ua.install.ensure_pos_page"
        self.assertLess(hooks.before_migrate.index(modules_hook), hooks.before_migrate.index(workspace_hook))
        self.assertLess(hooks.after_install.index(modules_hook), hooks.after_install.index(page_hook))
        self.assertLess(hooks.after_install.index(workspace_hook), hooks.after_install.index(page_hook))
        self.assertLess(hooks.after_migrate.index(modules_hook), hooks.after_migrate.index(page_hook))
        self.assertLess(hooks.after_migrate.index(workspace_hook), hooks.after_migrate.index(page_hook))

    def test_pos_uses_policy_aware_identification_endpoint(self):
        source = (APP / "ua_pos" / "page" / "ua_pos" / "ua_pos.js").read_text(
            encoding="utf-8"
        )
        self.assertIn('identificationApi("begin_pos"', source)
        self.assertIn("config.pos_channel", source)
        self.assertIn("config.allow_pos_channel_selection", source)
        self.assertNotIn('identificationApi("begin",', source)

    def test_employee_login_uses_plain_auto_generated_ean13(self):
        install = (APP / "install.py").read_text(encoding="utf-8")
        api = (APP / "ua_pos" / "api.py").read_text(encoding="utf-8")
        barcode = (APP / "ua_pos" / "employee_barcode.py").read_text(encoding="utf-8")

        self.assertIn('"fieldname": "ua_pos_barcode"', install)
        self.assertIn('"label": "Штрихкод касира (EAN-13)"', install)
        self.assertIn('"read_only": 1', install)
        self.assertIn("backfill_employee_barcodes()", install)
        self.assertIn('"ua_pos_barcode": barcode', api)
        self.assertNotIn('"ua_pos_barcode_hash": digest(barcode)', api)
        self.assertIn('EAN13_PREFIX = "9910"', barcode)
        self.assertIn('NAMING_SERIES = f"{EAN13_PREFIX}.{SEQUENCE_DIGITS *', barcode)
        self.assertEqual(
            hooks.doc_events["Employee"]["before_validate"],
            "erpnext_ua.ua_pos.employee_barcode.assign_employee_barcode",
        )

    def test_pos_login_has_no_test_cashier_and_uses_a_dark_heading(self):
        source = (APP / "ua_pos" / "page" / "ua_pos" / "ua_pos.js").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("POS-TEST-CASHIER", source)
        self.assertNotIn("Тестовий касир", source)
        self.assertIn(".ua-pos-login-card h1{font-size:27px;margin:32px 0 6px;color:var(--ink)}", source)
        self.assertIn(
            ".ua-pos input,.ua-pos select{color:#101828!important;"
            "-webkit-text-fill-color:#101828!important;caret-color:#101828}",
            source,
        )
        self.assertIn(
            ".ua-pos input::placeholder{color:#667085!important;"
            "-webkit-text-fill-color:#667085!important;opacity:1}",
            source,
        )
        self.assertIn(
            ".ua-pos-login-desk:disabled{color:#101828!important;"
            "-webkit-text-fill-color:#101828!important;opacity:1}",
            source,
        )

    def test_pos_workspace_is_visible_and_opens_the_cashier_page(self):
        workspace = json.loads(
            (
                APP
                / "ua_pos"
                / "workspace"
                / "ua_pos_workspace"
                / "ua_pos_workspace.json"
            ).read_text(encoding="utf-8")
        )
        self.assertTrue(workspace["public"])
        self.assertFalse(workspace["is_hidden"])
        self.assertEqual(workspace["name"], "UA POS Workspace")
        self.assertTrue(
            any(
                link.get("link_type") == "Page"
                and link.get("link_to") == "ua-pos"
                for link in workspace["links"]
            )
        )

        icon = json.loads(
            (APP / "desktop_icon" / "ua_pos_workspace.json").read_text(encoding="utf-8")
        )
        self.assertEqual(icon["parent_icon"], "ERPNext Ukraine")
        self.assertEqual(icon["link_to"], workspace["name"])
        self.assertFalse(icon["hidden"])

        sidebar = json.loads(
            (APP / "workspace_sidebar" / "ua_pos_workspace.json").read_text(encoding="utf-8")
        )
        self.assertEqual(sidebar["name"], workspace["name"])


if __name__ == "__main__":
    unittest.main()

# Ukrainian translations

`erpnext_ua/translations/uk.csv` is the authoritative Ukrainian catalog shipped
with this app. It intentionally includes Frappe and ERPNext messages: Frappe
loads translation catalogs in installed-app order, and `erpnext_ua` is required
to be installed after ERPNext.

Frappe v16 uses gettext for core apps, but continues to support CSV catalogs in
custom apps. CSV is used here because a single catalog must cover messages owned
by several apps. It is loaded directly at runtime and does not require database
`Translation` fixtures or a custom installation hook.

## Maintenance

The initial catalog was migrated from reviewed Ukrainian `Translation` records
on the reference ERPNext v16 site. Official Frappe and ERPNext v15 Ukrainian
catalogs are used as a lower-priority fallback for source strings that remain
unchanged in v16 (Frappe commit `105b17938839f4e5c6cdff817d42afc40c3bcc32`,
ERPNext commit `41038979ec51a7f4f3f0cabd6d308751da8dd5c9`). Production
translations and reviewed overrides always win.

Duplicate keys were resolved deterministically, identity translations were
omitted, placeholders were validated, and site-specific values were removed.
Against the reference Frappe 16.25 / ERPNext 16.26 source tree, the initial
catalog covers 57.5% of Frappe messages and 90.5% of ERPNext messages. Missing
messages safely fall back to their source text.

For a future refresh:

1. Export Ukrainian `Translation` rows to JSON without modifying the source
   site.
2. Review `tools/uk_translation_overrides.csv`.
3. Run:

   ```bash
   python3 tools/build_uk_translation_catalog.py \
     --input /path/to/export.json \
     --fallback /path/to/frappe-v15/frappe/translations/uk.csv \
     --fallback /path/to/erpnext-v15/erpnext/translations/uk.csv \
     --overrides tools/uk_translation_overrides.csv \
     --output erpnext_ua/translations/uk.csv \
     --report /tmp/uk-translation-report.json
   ```

4. Run `python3 -m unittest erpnext_ua.tests.test_translations`.
5. Verify representative Desk pages on a clean test site with no Ukrainian
   records in the `Translation` DocType.

Database `Translation` records take precedence over app catalogs. Existing
sites should migrate or remove their Ukrainian database overrides only after
the app catalog has been deployed and verified.

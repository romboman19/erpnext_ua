#!/usr/bin/env python3
"""Build a deterministic Ukrainian CSV catalog from exported Translation rows.

This is a development-time migration utility. Runtime translation loading stays
entirely within Frappe's standard custom-app CSV mechanism.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path


BRACE_PLACEHOLDER = re.compile(r"(?<!\{)\{(?:[A-Za-z_][A-Za-z0-9_.]*|\d+)\}(?!\})")
PRINTF_PLACEHOLDER = re.compile(r"%(?:\([^)]+\))?[#0+\-]*\d*(?:\.\d+)?[diouxXeEfFgGcrs]")
TEMPLATE_PLACEHOLDER = re.compile(r"\$\{[^{}]+\}")
EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def placeholder_signature(value: str) -> list[str]:
	return sorted(
		BRACE_PLACEHOLDER.findall(value)
		+ PRINTF_PLACEHOLDER.findall(value)
		+ TEMPLATE_PLACEHOLDER.findall(value)
	)


def read_overrides(path: Path) -> dict[tuple[str, str], str]:
	translations: dict[tuple[str, str], str] = {}
	if not path.exists():
		return translations

	with path.open(encoding="utf-8", newline="") as source:
		for row_number, row in enumerate(csv.reader(source), start=1):
			if len(row) not in (2, 3):
				raise ValueError(f"{path}:{row_number}: expected 2 or 3 columns, got {len(row)}")
			message, translation = row[:2]
			context = row[2] if len(row) == 3 else ""
			translations[(message, context)] = translation
	return translations


def is_safe_translation(message: str, translation: str) -> bool:
	return (
		bool(message)
		and bool(translation)
		and message != translation
		and placeholder_signature(message) == placeholder_signature(translation)
		and sorted(EMAIL.findall(message)) == sorted(EMAIL.findall(translation))
	)


def choose_translations(rows: list[dict]) -> tuple[dict[tuple[str, str], str], list[dict]]:
	grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
	for row in rows:
		message = row.get("source_text") or ""
		translation = (row.get("translated_text") or "").strip()
		context = row.get("context") or ""
		if not message or not translation:
			continue
		row = {**row, "source_text": message, "translated_text": translation, "context": context}
		grouped[(message, context)].append(row)

	selected: dict[tuple[str, str], str] = {}
	conflicts: list[dict] = []
	for key, candidates in grouped.items():
		candidates.sort(key=lambda row: (row.get("creation") or "", row.get("modified") or "", row.get("name") or ""))
		meaningful = [row for row in candidates if row["translated_text"] != row["source_text"]]
		meaningful = [row for row in meaningful if is_safe_translation(row["source_text"], row["translated_text"])]
		if not meaningful:
			continue

		winner = meaningful[-1]
		selected[key] = winner["translated_text"]
		variants = sorted({row["translated_text"] for row in candidates})
		if len(variants) > 1:
			conflicts.append(
				{
					"source_text": key[0],
					"context": key[1],
					"selected": winner["translated_text"],
					"variants": variants,
				}
			)
	return selected, conflicts


def main() -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument("--input", type=Path, required=True, help="JSON exported from the Translation DocType")
	parser.add_argument(
		"--fallback",
		type=Path,
		action="append",
		default=[],
		help="Older trusted CSV catalog used only when the export has no reviewed translation; repeatable",
	)
	parser.add_argument(
		"--overrides",
		type=Path,
		required=True,
		help="Reviewed entries that take precedence over the export",
	)
	parser.add_argument("--output", type=Path, required=True)
	parser.add_argument("--report", type=Path, required=True)
	args = parser.parse_args()

	rows = json.loads(args.input.read_text(encoding="utf-8"))
	translations: dict[tuple[str, str], str] = {}
	for fallback in args.fallback:
		translations.update(
			{
				key: value
				for key, value in read_overrides(fallback).items()
				if is_safe_translation(key[0], value)
			}
		)

	exported_translations, conflicts = choose_translations(rows)
	translations.update(exported_translations)
	translations.update(read_overrides(args.overrides))

	placeholder_mismatches = []
	for (message, context), translation in translations.items():
		if placeholder_signature(message) != placeholder_signature(translation):
			placeholder_mismatches.append(
				{
					"source_text": message,
					"context": context,
					"translation": translation,
					"source_placeholders": placeholder_signature(message),
					"translation_placeholders": placeholder_signature(translation),
				}
			)

	args.output.parent.mkdir(parents=True, exist_ok=True)
	with args.output.open("w", encoding="utf-8", newline="") as output:
		writer = csv.writer(output, lineterminator="\n")
		for (message, context), translation in sorted(translations.items(), key=lambda item: item[0]):
			writer.writerow([message, translation, context])

	report = {
		"exported_rows": len(rows),
		"catalog_entries": len(translations),
		"conflicts": conflicts,
		"placeholder_mismatches": placeholder_mismatches,
	}
	args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
	print(
		f"entries={len(translations)} conflicts={len(conflicts)} "
		f"placeholder_mismatches={len(placeholder_mismatches)} output={args.output}"
	)


if __name__ == "__main__":
	main()

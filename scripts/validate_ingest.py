#!/usr/bin/env python3
"""Validate a DBabel ingest report and its coverage semantics."""
import argparse
import json
from pathlib import Path
from typing import Iterable, List

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas" / "ingest_report.schema.json"


def _format_schema_errors(errors: Iterable) -> List[str]:
    result = []
    for error in sorted(errors, key=lambda e: list(e.absolute_path)):
        location = ".".join(str(x) for x in error.absolute_path) or "<root>"
        result.append("schema {}: {}".format(location, error.message))
    return result


def validate_ingest_report(report: dict) -> List[str]:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    errors = _format_schema_errors(Draft202012Validator(schema).iter_errors(report))
    if errors:
        return errors

    status = report["status"]
    structure = report["structure"]
    structure_status = structure["status"]
    uninspected = structure["uninspected"]
    limitations = report["limitations"]

    if status == "PASS":
        if not report["locations_available"]:
            errors.append("PASS requires stable locations")
        if structure_status not in {"VERIFIED", "NOT_APPLICABLE"}:
            errors.append("PASS requires VERIFIED or NOT_APPLICABLE structure status")
        if uninspected:
            errors.append("PASS cannot contain uninspected structures")
        if limitations:
            errors.append("PASS cannot contain unresolved limitations")

    if status == "PARTIAL":
        if not limitations and not uninspected:
            errors.append("PARTIAL requires explicit limitations or uninspected structures")

    if status == "FAIL" and not limitations:
        errors.append("FAIL requires at least one limitation/blocker")

    if structure_status == "PARTIAL" and not uninspected:
        errors.append("PARTIAL structure status requires uninspected structures")

    if structure_status == "VERIFIED" and uninspected:
        errors.append("VERIFIED structure status cannot contain uninspected structures")

    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()

    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        errors = validate_ingest_report(report)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(2, "Cannot read ingest report: {}\n".format(exc))

    if errors:
        parser.exit(1, "\n".join(errors) + "\n")

    print("Ingest report valid.")


if __name__ == "__main__":
    main()

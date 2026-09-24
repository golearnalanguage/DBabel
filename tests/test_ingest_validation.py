import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from validate_ingest import validate_ingest_report


def base_report():
    return {
        "format_version": "1.0",
        "source": "manual.docx",
        "format": "docx",
        "backend": "native_agent",
        "status": "PASS",
        "units_extracted": 12,
        "locations_available": True,
        "structure": {
            "status": "VERIFIED",
            "inspected": ["paragraphs", "tables"],
            "uninspected": [],
        },
        "warnings": [],
        "limitations": [],
    }


class IngestValidationTests(unittest.TestCase):
    def test_valid_pass(self):
        self.assertEqual(validate_ingest_report(base_report()), [])

    def test_pass_allows_not_applicable_structure(self):
        report = base_report()
        report["format"] = "txt"
        report["structure"] = {
            "status": "NOT_APPLICABLE",
            "inspected": ["lines"],
            "uninspected": [],
        }
        self.assertEqual(validate_ingest_report(report), [])

    def test_pass_requires_locations(self):
        report = base_report()
        report["locations_available"] = False
        self.assertIn("PASS requires stable locations", validate_ingest_report(report))

    def test_pass_rejects_partial_structure(self):
        report = base_report()
        report["structure"]["status"] = "PARTIAL"
        report["structure"]["uninspected"] = ["comments"]
        errors = validate_ingest_report(report)
        self.assertTrue(any("PASS requires VERIFIED" in x for x in errors))

    def test_pass_rejects_uninspected_structures(self):
        report = base_report()
        report["structure"]["uninspected"] = ["notes"]
        errors = validate_ingest_report(report)
        self.assertTrue(any("PASS cannot contain uninspected" in x for x in errors))

    def test_partial_requires_explicit_gap(self):
        report = base_report()
        report["status"] = "PARTIAL"
        report["structure"]["status"] = "UNVERIFIED"
        errors = validate_ingest_report(report)
        self.assertIn(
            "PARTIAL requires explicit limitations or uninspected structures",
            errors,
        )

    def test_valid_partial_with_gap(self):
        report = base_report()
        report["status"] = "PARTIAL"
        report["structure"]["status"] = "PARTIAL"
        report["structure"]["uninspected"] = ["comments"]
        report["limitations"] = ["Comments were not exposed by the parser."]
        self.assertEqual(validate_ingest_report(report), [])

    def test_fail_requires_blocker(self):
        report = base_report()
        report["status"] = "FAIL"
        report["structure"]["status"] = "UNVERIFIED"
        report["locations_available"] = False
        self.assertIn(
            "FAIL requires at least one limitation/blocker",
            validate_ingest_report(report),
        )

    def test_schema_rejects_unknown_field(self):
        report = base_report()
        report["unexpected"] = True
        errors = validate_ingest_report(report)
        self.assertTrue(any("Additional properties" in x for x in errors))


if __name__ == "__main__":
    unittest.main()

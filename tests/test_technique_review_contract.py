import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(
        0,
        str(SCRIPTS),
    )

from review_model import (
    deterministic_issue_to_review,
    semantic_finding_to_review,
    validate_against_schema,
)
from validate_report import validate_report


def annotation():
    return {
        "technique_id": (
            "TERMINOLOGY_VARIANT_GOVERNANCE"
        ),
        "risk": "MEDIUM",
        "transformations": [
            "TERM_SUBSTITUTION"
        ],
        "quality_dimensions": [
            "TERMINOLOGY"
        ],
        "trigger_reason": (
            "The target uses a non-approved "
            "terminology variant."
        ),
    }


class TechniqueReviewContractTests(
    unittest.TestCase
):
    def setUp(self):
        self.report = json.loads(
            (
                ROOT
                / "examples"
                / "audit_report.json"
            ).read_text(
                encoding="utf-8"
            )
        )

    def test_valid_technique_annotation(self):
        self.report[
            "findings"
        ][0]["technique"] = annotation()

        self.assertEqual(
            validate_report(
                self.report
            ),
            [],
        )

    def test_unknown_technique_rejected(self):
        value = annotation()
        value["technique_id"] = (
            "UNKNOWN_TECHNIQUE"
        )

        self.report[
            "findings"
        ][0]["technique"] = value

        errors = validate_report(
            self.report
        )

        self.assertTrue(
            any(
                "unknown technique_id"
                in error
                for error in errors
            ),
            errors,
        )

    def test_risk_must_match_catalog(self):
        value = annotation()
        value["risk"] = "HIGH"

        self.report[
            "findings"
        ][0]["technique"] = value

        errors = validate_report(
            self.report
        )

        self.assertTrue(
            any(
                "does not match catalog risk"
                in error
                for error in errors
            ),
            errors,
        )

    def test_transformation_must_belong_to_technique(self):
        value = annotation()
        value[
            "transformations"
        ] = [
            "SENTENCE_MERGE"
        ]

        self.report[
            "findings"
        ][0]["technique"] = value

        errors = validate_report(
            self.report
        )

        self.assertTrue(
            any(
                "not declared"
                in error
                for error in errors
            ),
            errors,
        )

    def test_quality_dimension_must_belong_to_technique(self):
        value = annotation()
        value[
            "quality_dimensions"
        ] = [
            "ACCURACY"
        ]

        self.report[
            "findings"
        ][0]["technique"] = value

        errors = validate_report(
            self.report
        )

        self.assertTrue(
            any(
                "quality dimensions"
                in error
                for error in errors
            ),
            errors,
        )

    def test_semantic_issue_carries_annotation(self):
        finding = copy.deepcopy(
            self.report[
                "findings"
            ][0]
        )

        finding["technique"] = (
            annotation()
        )

        issue = (
            semantic_finding_to_review(
                finding,
                "U1",
            )
        )

        self.assertEqual(
            issue[
                "technique"
            ][
                "technique_id"
            ],
            "TERMINOLOGY_VARIANT_GOVERNANCE",
        )

        schema = (
            ROOT
            / "schemas"
            / "review_issue.schema.json"
        )

        self.assertEqual(
            validate_against_schema(
                issue,
                schema,
            ),
            [],
        )

    def test_trigger_wording_does_not_churn_fingerprint(self):
        finding = copy.deepcopy(
            self.report[
                "findings"
            ][0]
        )

        finding["technique"] = (
            annotation()
        )

        first = (
            semantic_finding_to_review(
                finding,
                "U1",
            )
        )

        finding[
            "technique"
        ][
            "trigger_reason"
        ] = (
            "Same failure mode, clearer "
            "explanation wording."
        )

        second = (
            semantic_finding_to_review(
                finding,
                "U1",
            )
        )

        self.assertEqual(
            first["fingerprint"],
            second["fingerprint"],
        )

    def test_deterministic_issue_cannot_claim_technique(self):
        issue = (
            deterministic_issue_to_review(
                {
                    "id": "Q1",
                    "unit_id": "U1",
                    "check_id": (
                        "NUMBER_INTEGRITY"
                    ),
                    "classification": (
                        "POTENTIAL_ISSUE"
                    ),
                    "severity": "ERROR",
                    "message": "number mismatch",
                    "source_items": ["1"],
                    "target_items": ["2"],
                }
            )
        )

        issue["technique"] = (
            annotation()
        )

        errors = (
            validate_against_schema(
                issue,
                (
                    ROOT
                    / "schemas"
                    / "review_issue.schema.json"
                ),
            )
        )

        self.assertTrue(
            errors
        )


if __name__ == "__main__":
    unittest.main()

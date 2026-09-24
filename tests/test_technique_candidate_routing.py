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

from suggest_translation_techniques import (
    TechniqueRoutingError,
    candidate_report_cross_errors,
    load_translation_registry,
    route_candidates,
    validate_candidate_report_schema,
    validate_signal_observations,
)


class TechniqueCandidateRoutingTests(
    unittest.TestCase
):
    def setUp(self):
        self.value = json.loads(
            (
                ROOT
                / "examples"
                / "technique_signal_observations.json"
            ).read_text(
                encoding="utf-8"
            )
        )

        self.registry = (
            load_translation_registry(
                ROOT
            )
        )

    def test_input_schema(self):
        self.assertEqual(
            validate_signal_observations(
                self.value
            ),
            [],
        )

    def test_exact_catalog_trigger_routing(self):
        report = route_candidates(
            self.value,
            self.registry,
        )

        ids = [
            item["technique_id"]
            for item in report[
                "units"
            ][0][
                "candidates"
            ]
        ]

        self.assertEqual(
            ids,
            [
                "MODAL_STRENGTH_PRESERVATION",
                "CONDITION_ACTION_RESULT_PRESERVATION",
                "SCOPE_PRESERVATION",
            ],
        )

    def test_ui_role_filters_candidates(self):
        report = route_candidates(
            self.value,
            self.registry,
        )

        ids = [
            item["technique_id"]
            for item in report[
                "units"
            ][1][
                "candidates"
            ]
        ]

        self.assertEqual(
            ids,
            [
                "UI_LABEL_ANCHORING"
            ],
        )

    def test_unmatched_signal_is_preserved(self):
        report = route_candidates(
            self.value,
            self.registry,
        )

        unit = report[
            "units"
        ][2]

        self.assertEqual(
            unit["candidates"],
            [],
        )

        self.assertEqual(
            unit[
                "unmatched_signals"
            ],
            [
                "synthetic_unmatched_signal"
            ],
        )

    def test_policy_is_non_authoritative(self):
        report = route_candidates(
            self.value,
            self.registry,
        )

        self.assertEqual(
            report["policy"],
            {
                "observations_are_evidence": False,
                "candidates_are_findings": False,
                "candidates_are_decisions": False,
                "candidates_authorize_repair": False,
                "candidates_are_human_approval": False,
            },
        )

    def test_metadata_is_catalog_derived(self):
        report = route_candidates(
            self.value,
            self.registry,
        )

        candidate = report[
            "units"
        ][0][
            "candidates"
        ][0]

        source = next(
            item
            for item in self.registry[
                "techniques"
            ]
            if item["id"]
            == candidate[
                "technique_id"
            ]
        )

        self.assertEqual(
            candidate["risk"],
            source["risk"],
        )

        self.assertEqual(
            candidate[
                "quality_dimensions"
            ],
            source[
                "qa_mapping"
            ][
                "semantic_dimensions"
            ],
        )

    def test_output_contract(self):
        report = route_candidates(
            self.value,
            self.registry,
        )

        self.assertEqual(
            validate_candidate_report_schema(
                report
            ),
            [],
        )

        self.assertEqual(
            candidate_report_cross_errors(
                report,
                self.registry,
            ),
            [],
        )

    def test_any_is_not_a_concrete_role(self):
        value = copy.deepcopy(
            self.value
        )

        value[
            "observations"
        ][0][
            "text_role"
        ] = "ANY"

        with self.assertRaises(
            TechniqueRoutingError
        ):
            route_candidates(
                value,
                self.registry,
            )

    def test_unknown_role_rejected(self):
        value = copy.deepcopy(
            self.value
        )

        value[
            "observations"
        ][0][
            "text_role"
        ] = "UNKNOWN_ROLE"

        with self.assertRaises(
            TechniqueRoutingError
        ):
            route_candidates(
                value,
                self.registry,
            )

    def test_duplicate_unit_rejected(self):
        value = copy.deepcopy(
            self.value
        )

        value[
            "observations"
        ].append(
            copy.deepcopy(
                value[
                    "observations"
                ][0]
            )
        )

        with self.assertRaises(
            TechniqueRoutingError
        ):
            route_candidates(
                value,
                self.registry,
            )

    def test_matching_is_exact_not_fuzzy(self):
        value = {
            "format_version": "1.0",
            "mode": "TRANSLATE",
            "observations": [
                {
                    "unit_id": "U1",
                    "text_role": "PROCEDURE",
                    "observed_signals": [
                        "must_like"
                    ]
                }
            ]
        }

        report = route_candidates(
            value,
            self.registry,
        )

        unit = report[
            "units"
        ][0]

        self.assertEqual(
            unit["candidates"],
            [],
        )

        self.assertEqual(
            unit[
                "unmatched_signals"
            ],
            [
                "must_like"
            ],
        )

    def test_cross_contract_detects_risk_drift(self):
        report = route_candidates(
            self.value,
            self.registry,
        )

        report = copy.deepcopy(
            report
        )

        report[
            "units"
        ][0][
            "candidates"
        ][0][
            "risk"
        ] = "LOW"

        errors = (
            candidate_report_cross_errors(
                report,
                self.registry,
            )
        )

        self.assertTrue(
            any(
                "risk drift"
                in error
                for error in errors
            ),
            errors,
        )

    def test_cross_contract_rejects_duplicate_report_unit_id(self):
        report = route_candidates(
            self.value,
            self.registry,
        )

        report = copy.deepcopy(
            report
        )

        report[
            "units"
        ].append(
            copy.deepcopy(
                report[
                    "units"
                ][0]
            )
        )

        errors = (
            candidate_report_cross_errors(
                report,
                self.registry,
            )
        )

        self.assertTrue(
            any(
                "duplicate unit_id"
                in error
                for error in errors
            ),
            errors,
        )


    def test_cross_contract_detects_signal_coverage_drift(self):
        report = route_candidates(
            self.value,
            self.registry,
        )

        report = copy.deepcopy(
            report
        )

        report[
            "units"
        ][2][
            "unmatched_signals"
        ] = []

        errors = (
            candidate_report_cross_errors(
                report,
                self.registry,
            )
        )

        self.assertTrue(
            any(
                "signal coverage mismatch"
                in error
                for error in errors
            ),
            errors,
        )


if __name__ == "__main__":
    unittest.main()

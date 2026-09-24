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

from check_bilingual_integrity import (
    load_units,
)
from extract_translation_signals import (
    SURFACE_SIGNAL_ALLOWLIST,
    SurfaceSignalError,
    extract_signal_observations,
    load_surface_rules,
    surface_rule_cross_errors,
    validate_surface_rules,
)
from suggest_translation_techniques import (
    route_candidates,
    validate_signal_observations,
)
from technique_contract import (
    load_translation_registry,
)


class SurfaceSignalExtractionTests(
    unittest.TestCase
):
    def setUp(self):
        self.rules = (
            load_surface_rules()
        )

        self.registry = (
            load_translation_registry(
                ROOT
            )
        )

        self.units = load_units(
            ROOT
            / "tests"
            / "fixtures"
            / "surface_signal_units.jsonl"
        )

    def test_rule_schema_and_cross_contract(self):
        self.assertEqual(
            validate_surface_rules(
                self.rules
            ),
            [],
        )

        self.assertEqual(
            surface_rule_cross_errors(
                self.rules,
                self.registry,
            ),
            [],
        )

    def test_literal_signals_reuse_accuracy_core_extractors(self):
        result = extract_signal_observations(
            self.units,
            "BILINGUAL_REVIEW",
            self.rules,
        )

        unit = result[
            "observations"
        ][0]

        signals = set(
            unit[
                "observed_signals"
            ]
        )

        for expected in {
            "placeholder",
            "url",
            "path",
            "filename",
            "environment_variable",
            "version_literal",
        }:
            self.assertIn(
                expected,
                signals,
            )

    def test_chinese_surface_modal_and_scope_signals(self):
        result = extract_signal_observations(
            self.units,
            "BILINGUAL_REVIEW",
            self.rules,
        )

        unit = result[
            "observations"
        ][0]

        signals = set(
            unit[
                "observed_signals"
            ]
        )

        for expected in {
            "must",
            "only",
            "current",
            "selected",
        }:
            self.assertIn(
                expected,
                signals,
            )

    def test_context_role_emits_ui_text_only_as_signal(self):
        result = extract_signal_observations(
            self.units,
            "BILINGUAL_REVIEW",
            self.rules,
        )

        unit = next(
            item
            for item in result[
                "observations"
            ]
            if item[
                "unit_id"
            ]
            == "U0002"
        )

        self.assertEqual(
            unit[
                "observed_signals"
            ],
            [
                "ui_text"
            ],
        )

        self.assertEqual(
            unit[
                "signal_details"
            ][0][
                "side"
            ],
            "CONTEXT",
        )

    def test_explicit_condition_and_causality_are_surface_cues(self):
        result = extract_signal_observations(
            self.units,
            "BILINGUAL_REVIEW",
            self.rules,
        )

        unit = next(
            item
            for item in result[
                "observations"
            ]
            if item[
                "unit_id"
            ]
            == "U0003"
        )

        signals = set(
            unit[
                "observed_signals"
            ]
        )

        for expected in {
            "conditional_clause",
            "because",
            "required",
            "all",
        }:
            self.assertIn(
                expected,
                signals,
            )

    def test_signal_details_cover_observed_signals(self):
        result = extract_signal_observations(
            self.units,
            "BILINGUAL_REVIEW",
            self.rules,
        )

        for unit in result[
            "observations"
        ]:
            detail_signals = []

            for detail in unit[
                "signal_details"
            ]:
                if (
                    detail[
                        "signal"
                    ]
                    not in detail_signals
                ):
                    detail_signals.append(
                        detail[
                            "signal"
                        ]
                    )

            self.assertEqual(
                unit[
                    "observed_signals"
                ],
                detail_signals,
            )

    def test_generated_output_matches_signal_schema(self):
        result = extract_signal_observations(
            self.units,
            "BILINGUAL_REVIEW",
            self.rules,
        )

        self.assertEqual(
            validate_signal_observations(
                result
            ),
            [],
        )

    def test_surface_output_routes_into_candidate_layer(self):
        observations = (
            extract_signal_observations(
                self.units,
                "BILINGUAL_REVIEW",
                self.rules,
            )
        )

        candidates = route_candidates(
            observations,
            self.registry,
        )

        ids = {
            candidate[
                "technique_id"
            ]
            for unit
            in candidates[
                "units"
            ]
            for candidate
            in unit[
                "candidates"
            ]
        }

        self.assertIn(
            "TECHNICAL_TOKEN_SHIELDING",
            ids,
        )

        self.assertIn(
            "MODAL_STRENGTH_PRESERVATION",
            ids,
        )

        self.assertIn(
            "SCOPE_PRESERVATION",
            ids,
        )

        self.assertIn(
            "TEXT_ROLE_TRANSLATION",
            ids,
        )

        self.assertIn(
            "NO_INVENTED_CAUSALITY",
            ids,
        )

    def test_semantic_only_triggers_are_not_allowlisted(self):
        forbidden = {
            "polysemy",
            "ambiguous_database_term",
            "cross_product_mapping",
            "role_sensitive_reordering",
            "multiple_actions",
            "ambiguous_attachment",
            "omitted_subject",
            "pronoun_resolution",
            "source_conflict",
            "scope_conflict",
            "probable_copy_error",
            "contradictory_instruction",
        }

        self.assertFalse(
            forbidden
            & SURFACE_SIGNAL_ALLOWLIST
        )

    def test_missing_language_skips_lexical_detection_but_keeps_literals(self):
        unit = copy.deepcopy(
            self.units[
                0
            ]
        )

        unit.pop(
            "source_language"
        )

        unit.pop(
            "target_language"
        )

        result = extract_signal_observations(
            [
                unit
            ],
            "BILINGUAL_REVIEW",
            self.rules,
        )

        self.assertTrue(
            result[
                "warnings"
            ]
        )

        signals = set(
            result[
                "observations"
            ][0][
                "observed_signals"
            ]
        )

        self.assertIn(
            "placeholder",
            signals,
        )

        self.assertNotIn(
            "must",
            signals,
        )

    def test_missing_text_role_fails_closed(self):
        unit = copy.deepcopy(
            self.units[
                0
            ]
        )

        unit[
            "context"
        ].pop(
            "text_role"
        )

        with self.assertRaises(
            SurfaceSignalError
        ):
            extract_signal_observations(
                [
                    unit
                ],
                "BILINGUAL_REVIEW",
                self.rules,
            )

    def test_ambiguous_alignment_is_rejected(self):
        unit = copy.deepcopy(
            self.units[
                0
            ]
        )

        unit[
            "alignment"
        ] = "AMBIGUOUS"

        with self.assertRaises(
            SurfaceSignalError
        ):
            extract_signal_observations(
                [
                    unit
                ],
                "BILINGUAL_REVIEW",
                self.rules,
            )

    def test_policy_is_explicitly_non_authoritative(self):
        result = extract_signal_observations(
            self.units,
            "BILINGUAL_REVIEW",
            self.rules,
        )

        self.assertEqual(
            result[
                "policy"
            ],
            {
                "surface_only": True,
                "semantic_inference_allowed": False,
                "signals_are_evidence": False,
                "signals_are_findings": False,
                "signals_authorize_repair": False,
                "signals_are_human_approval": False,
            },
        )


if __name__ == "__main__":
    unittest.main()

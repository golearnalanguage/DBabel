import copy
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

from build_translation_review_intake import (
    TranslationReviewIntakeError,
    build_translation_review_intake,
    intake_cross_errors,
    validate_translation_review_intake,
)


def unit(
    unit_id,
    source,
    target,
    role="PROCEDURE",
    source_language="en",
    target_language="en",
):
    return {
        "id": unit_id,
        "source": source,
        "target": target,
        "source_language": source_language,
        "target_language": target_language,
        "alignment": "ALIGNED",
        "context": {
            "text_role": role
        },
    }


class TranslationReviewIntakeTests(
    unittest.TestCase
):
    def test_bilingual_review_runs_qa_and_semantic_handoff(self):
        value = build_translation_review_intake(
            [
                unit(
                    "U1",
                    "Keep {id}.",
                    "Keep {id}.",
                )
            ],
            "BILINGUAL_REVIEW",
        )

        self.assertEqual(
            value["phase"],
            "BILINGUAL_REVIEW",
        )

        self.assertEqual(
            value[
                "deterministic_qa"
            ][
                "status"
            ],
            "RUN",
        )

        self.assertEqual(
            value[
                "handoff"
            ][
                "next_state"
            ],
            "ADJUDICATION",
        )

    def test_pre_translation_skips_deterministic_qa(self):
        value = build_translation_review_intake(
            [
                unit(
                    "U1",
                    "You must keep {id}.",
                    "",
                )
            ],
            "TRANSLATE",
        )

        self.assertEqual(
            value["phase"],
            "PRE_TRANSLATION",
        )

        self.assertEqual(
            value[
                "deterministic_qa"
            ],
            {
                "status": "NOT_RUN",
                "reason": (
                    "Target text is not yet available; "
                    "deterministic bilingual QA is deferred until post-translation."
                ),
                "report": None,
            },
        )

        self.assertEqual(
            value[
                "handoff"
            ][
                "status"
            ],
            "READY_FOR_TRANSLATION",
        )

    def test_post_translation_runs_qa(self):
        value = build_translation_review_intake(
            [
                unit(
                    "U1",
                    "You must keep {id}.",
                    "You must keep {id}.",
                )
            ],
            "TRANSLATE",
        )

        self.assertEqual(
            value["phase"],
            "POST_TRANSLATION",
        )

        self.assertEqual(
            value[
                "deterministic_qa"
            ][
                "status"
            ],
            "RUN",
        )

        self.assertEqual(
            value[
                "handoff"
            ][
                "status"
            ],
            "READY_FOR_SEMANTIC_ADJUDICATION",
        )

    def test_translate_mixed_target_readiness_fails_closed(self):
        units = [
            unit(
                "U1",
                "Keep this.",
                "",
            ),
            unit(
                "U2",
                "Keep that.",
                "Keep that.",
            ),
        ]

        with self.assertRaises(
            TranslationReviewIntakeError
        ):
            build_translation_review_intake(
                units,
                "TRANSLATE",
            )

    def test_bilingual_review_requires_target(self):
        with self.assertRaises(
            TranslationReviewIntakeError
        ):
            build_translation_review_intake(
                [
                    unit(
                        "U1",
                        "Keep this.",
                        "",
                    )
                ],
                "BILINGUAL_REVIEW",
            )

    def test_signal_contrasts_remain_mechanical(self):
        value = build_translation_review_intake(
            [
                unit(
                    "U1",
                    "You must keep all files.",
                    "You should keep all files.",
                )
            ],
            "BILINGUAL_REVIEW",
        )

        contrast = value[
            "signal_contrasts"
        ][0]

        self.assertIn(
            "all",
            contrast[
                "shared"
            ],
        )

        self.assertIn(
            "must",
            contrast[
                "source_only"
            ],
        )

        self.assertIn(
            "should",
            contrast[
                "target_only"
            ],
        )

    def test_context_signal_is_kept_separate(self):
        value = build_translation_review_intake(
            [
                unit(
                    "U1",
                    "Start",
                    "Start",
                    role="UI_LABEL",
                )
            ],
            "BILINGUAL_REVIEW",
        )

        contrast = value[
            "signal_contrasts"
        ][0]

        self.assertEqual(
            contrast[
                "context_signals"
            ],
            [
                "ui_text"
            ],
        )

    def test_qa_issue_remains_potential_issue(self):
        value = build_translation_review_intake(
            [
                unit(
                    "U1",
                    "Keep {id}.",
                    "Keep id.",
                )
            ],
            "BILINGUAL_REVIEW",
        )

        issues = value[
            "deterministic_qa"
        ][
            "report"
        ][
            "issues"
        ]

        self.assertTrue(
            issues
        )

        self.assertTrue(
            all(
                issue[
                    "classification"
                ]
                == "POTENTIAL_ISSUE"
                for issue
                in issues
            )
        )

    def test_schema_and_cross_contract_are_clean(self):
        value = build_translation_review_intake(
            [
                unit(
                    "U1",
                    "You must keep all files.",
                    "You must keep all files.",
                )
            ],
            "BILINGUAL_REVIEW",
        )

        self.assertEqual(
            validate_translation_review_intake(
                value
            ),
            [],
        )

        self.assertEqual(
            intake_cross_errors(
                value
            ),
            [],
        )

    def test_cross_contract_detects_contrast_drift(self):
        value = build_translation_review_intake(
            [
                unit(
                    "U1",
                    "You must keep all files.",
                    "You should keep all files.",
                )
            ],
            "BILINGUAL_REVIEW",
        )

        value = copy.deepcopy(
            value
        )

        value[
            "signal_contrasts"
        ][0][
            "source_only"
        ] = []

        errors = intake_cross_errors(
            value
        )

        self.assertTrue(
            any(
                "signal contrast drift"
                in error
                for error in errors
            ),
            errors,
        )

    def test_policy_is_non_authoritative(self):
        value = build_translation_review_intake(
            [
                unit(
                    "U1",
                    "Keep this.",
                    "Keep this.",
                )
            ],
            "BILINGUAL_REVIEW",
        )

        self.assertEqual(
            value[
                "policy"
            ],
            {
                "surface_signals_are_evidence": False,
                "surface_signals_are_findings": False,
                "technique_candidates_are_findings": False,
                "deterministic_qa_is_semantic_verdict": False,
                "intake_authorizes_repair": False,
                "intake_is_human_approval": False,
            },
        )


if __name__ == "__main__":
    unittest.main()

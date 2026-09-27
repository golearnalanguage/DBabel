import json
import unittest

from runtime.models import GenerationResponse
from runtime.semantic_adjudication import (
    SemanticAdjudicationError,
    SemanticLimits,
    adjudicate_semantics,
    batch_units,
    parse_response,
)
from validate_report import validate_report


class FakeProvider:
    def __init__(self, response):
        self.response = response

    def generate(self, request):
        return GenerationResponse(
            text=json.dumps(
                self.response,
                ensure_ascii=False,
            ),
            model="fake-semantic-model",
            provider="fake-provider",
            response_id="semantic-1",
            usage={
                "total_tokens": 12,
            },
        )


def post_translation():
    return {
        "format_version": "1.0",
        "status":
            "POST_TRANSLATION_QA_READY",
        "completion_allowed":
            False,
        "review_units": [{
            "id": "U00001_en",
            "location": "line:1",
            "source": "配置主库",
            "target": "",
            "source_language":
                "zh-CN",
            "target_language":
                "en",
            "alignment":
                "ALIGNED",
            "context": {
                "text_role":
                    "PROSE",
            },
            "suggested_target":
                "Configure the primary database.",
            "proposal_decision":
                "REPLACE",
            "suggestion_reason":
                "translation",
            "qa_issue_ids": [],
        }],
        "deterministic_qa": {
            "format_version": "1.0",
            "summary": {
                "units_checked": 1,
                "error_count": 0,
                "warning_count": 0,
            },
            "checks_run": [],
            "issues": [],
        },
    }


class SemanticAdjudicationTests(
    unittest.TestCase
):
    def test_no_finding_is_not_approval(
        self,
    ):
        result = adjudicate_semantics(
            provider=FakeProvider({
                "units": [{
                    "id": "U00001_en",
                    "outcome":
                        "NO_FINDING",
                    "classification":
                        None,
                    "reason":
                        "No semantic risk surfaced in the supplied context.",
                    "next_action":
                        "",
                }]
            }),
            post_translation=
                post_translation(),
            source_language="zh-CN",
            target_language="en",
            document_name=
                "source.txt",
        )

        self.assertEqual(
            result["status"],
            "SEMANTIC_ADJUDICATION_READY",
        )

        self.assertFalse(
            result[
                "completion_allowed"
            ]
        )

        self.assertEqual(
            result["finding_count"],
            0,
        )

        self.assertEqual(
            validate_report(
                result[
                    "audit_report"
                ]
            ),
            [],
        )

        self.assertEqual(
            result["next_state"],
            "REVIEW_SESSION_BINDING",
        )

    def test_review_finding_has_no_fake_evidence(
        self,
    ):
        result = adjudicate_semantics(
            provider=FakeProvider({
                "units": [{
                    "id": "U00001_en",
                    "outcome": "REVIEW",
                    "classification":
                        "VENDOR_CONCEPT",
                    "reason":
                        "Primary database may have product-specific terminology.",
                    "next_action":
                        "Confirm the applicable product terminology.",
                }]
            }),
            post_translation=
                post_translation(),
            source_language="zh-CN",
            target_language="en",
            document_name=
                "source.txt",
        )

        finding = result[
            "audit_report"
        ]["findings"][0]

        self.assertEqual(
            finding["decision"],
            "REVIEW",
        )

        self.assertEqual(
            finding["confidence"],
            "REVIEW_REQUIRED",
        )

        self.assertEqual(
            finding["evidence_refs"],
            [],
        )

        self.assertNotIn(
            "recommendation",
            finding,
        )

    def test_out_of_scope_claim_is_routed_not_verified(
        self,
    ):
        value = post_translation()

        value["review_units"][0][
            "source"
        ] = (
            "产品 A 的性能比产品 B 高 40%。"
        )

        value["review_units"][0][
            "suggested_target"
        ] = (
            "Product A performs 40% better than Product B."
        )

        result = adjudicate_semantics(
            provider=FakeProvider({
                "units": [{
                    "id": "U00001_en",
                    "outcome":
                        "OUT_OF_SCOPE_CLAIM",
                    "classification":
                        "TECHNICAL_CLAIM",
                    "reason":
                        "The performance comparison requires separate benchmark evidence.",
                    "next_action":
                        "Request applicable benchmark methodology and measurements.",
                }]
            }),
            post_translation=value,
            source_language="zh-CN",
            target_language="en",
            document_name=
                "source.txt",
        )

        finding = result[
            "audit_report"
        ]["findings"][0]

        self.assertTrue(
            finding[
                "technical_claim"
            ]
        )

        self.assertEqual(
            finding["decision"],
            "OUT_OF_SCOPE_CLAIM",
        )

    def test_replacement_outcome_is_rejected(
        self,
    ):
        batch = (
            post_translation()[
                "review_units"
            ]
        )

        response = json.dumps({
            "units": [{
                "id": "U00001_en",
                "outcome": "REPLACE",
                "classification":
                    "VENDOR_CONCEPT",
                "reason":
                    "model wants replacement",
                "next_action":
                    "replace it",
            }]
        })

        with self.assertRaises(
            SemanticAdjudicationError
        ):
            parse_response(
                response,
                batch,
            )

    def test_extra_authority_field_is_rejected(
        self,
    ):
        batch = (
            post_translation()[
                "review_units"
            ]
        )

        response = json.dumps({
            "units": [{
                "id": "U00001_en",
                "outcome":
                    "NO_FINDING",
                "classification":
                    None,
                "reason":
                    "none",
                "next_action":
                    "",
                "approved_target":
                    "forbidden",
            }]
        })

        with self.assertRaises(
            SemanticAdjudicationError
        ):
            parse_response(
                response,
                batch,
            )

    def test_ids_must_match_exactly(
        self,
    ):
        batch = (
            post_translation()[
                "review_units"
            ]
        )

        response = json.dumps({
            "units": [{
                "id": "WRONG_ID",
                "outcome":
                    "NO_FINDING",
                "classification":
                    None,
                "reason":
                    "none",
                "next_action":
                    "",
            }]
        })

        with self.assertRaises(
            SemanticAdjudicationError
        ):
            parse_response(
                response,
                batch,
            )

    def test_single_unit_over_character_limit_fails_closed(
        self,
    ):
        units = (
            post_translation()[
                "review_units"
            ]
        )

        # Force one individual unit above the configured
        # 512-character batch ceiling. This tests the
        # fail-closed oversized-unit path rather than merely
        # exercising a normal short fixture.
        units[0]["source"] = (
            "配置主库" * 100
        )
        units[0]["suggested_target"] = (
            "Configure the primary database. " * 20
        )

        with self.assertRaises(
            SemanticAdjudicationError
        ):
            batch_units(
                units,
                SemanticLimits(
                    max_units_per_batch=20,
                    max_chars_per_batch=512,
                ),
            )

    def test_combined_character_limit_splits_batches(
        self,
    ):
        first = (
            post_translation()[
                "review_units"
            ][0]
        )

        second = dict(first)
        second["id"] = "U00002_en"
        second["location"] = "line:2"
        second["context"] = dict(
            first["context"]
        )

        first["source"] = (
            "甲" * 150
        )
        first["suggested_target"] = (
            "A" * 150
        )

        second["source"] = (
            "乙" * 150
        )
        second["suggested_target"] = (
            "B" * 150
        )

        batches = batch_units(
            [first, second],
            SemanticLimits(
                max_units_per_batch=20,
                max_chars_per_batch=512,
            ),
        )

        self.assertEqual(
            [
                [unit["id"] for unit in batch]
                for batch in batches
            ],
            [
                ["U00001_en"],
                ["U00002_en"],
            ],
        )


if __name__ == "__main__":
    unittest.main()

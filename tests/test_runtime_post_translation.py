import unittest

from runtime.post_translation import (
    PostTranslationError,
    prepare_post_translation,
)


def proposal(
    *,
    source,
    suggested,
    decision="REPLACE",
    unit_id="U00001_en",
):
    return {
        "format_version": "1.0",
        "status": "TRANSLATION_PROPOSED",
        "completion_allowed": False,
        "batch_count": 1,
        "unit_count": 1,
        "receipts": [],
        "units": [{
            "id": unit_id,
            "location": "line:1",
            "source": source,
            "target": "",
            "source_language": "zh-CN",
            "target_language": "en",
            "alignment": "ALIGNED",
            "context": {
                "text_role": "PROSE",
            },
            "suggested_target": suggested,
            "proposal_decision": decision,
            "suggestion_reason": "test proposal",
        }],
    }


class PostTranslationTests(
    unittest.TestCase
):
    def test_suggested_target_is_selected_for_qa(
        self,
    ):
        result = prepare_post_translation(
            proposal(
                source="配置主库",
                suggested=(
                    "Configure the primary database."
                ),
            ),
            source_language="zh-CN",
            target_language="en",
        )

        self.assertEqual(
            result["status"],
            "POST_TRANSLATION_QA_READY",
        )

        self.assertFalse(
            result["completion_allowed"]
        )

        self.assertEqual(
            result["qa_target_units"][0]["target"],
            "Configure the primary database.",
        )

        self.assertEqual(
            result[
                "qa_target_receipt"
            ]["selection"][0]["selected_from"],
            "suggested_target",
        )

        self.assertEqual(
            result[
                "translation_review_intake"
            ]["phase"],
            "POST_TRANSLATION",
        )

        self.assertEqual(
            result["handoff"]["status"],
            "READY_FOR_SEMANTIC_ADJUDICATION",
        )

    def test_review_unit_remains_proposal_only(
        self,
    ):
        result = prepare_post_translation(
            proposal(
                source="配置主库",
                suggested=(
                    "Configure the primary database."
                ),
            ),
            source_language="zh-CN",
            target_language="en",
        )

        unit = result[
            "review_units"
        ][0]

        self.assertEqual(
            unit["target"],
            "",
        )

        self.assertEqual(
            unit["suggested_target"],
            "Configure the primary database.",
        )

        self.assertNotIn(
            "approved_target",
            unit,
        )

    def test_cross_language_identity_replace_fails_closed(
        self,
    ):
        with self.assertRaises(
            PostTranslationError
        ):
            prepare_post_translation(
                proposal(
                    source="DM8",
                    suggested="DM8",
                    decision="REPLACE",
                ),
                source_language="zh-CN",
                target_language="en",
            )

    def test_explicit_protect_identity_is_allowed(
        self,
    ):
        result = prepare_post_translation(
            proposal(
                source="DM8",
                suggested="DM8",
                decision="PROTECT",
            ),
            source_language="zh-CN",
            target_language="en",
        )

        self.assertEqual(
            result[
                "qa_target_units"
            ][0]["target"],
            "DM8",
        )

    def test_number_change_becomes_potential_issue(
        self,
    ):
        result = prepare_post_translation(
            proposal(
                source="端口为 5236。",
                suggested="The port is 5237.",
            ),
            source_language="zh-CN",
            target_language="en",
        )

        report = result[
            "deterministic_qa"
        ]

        issues = report.get(
            "issues",
            []
        )

        self.assertTrue(
            any(
                issue.get("check_id")
                == "NUMBER_INTEGRITY"
                and issue.get("classification")
                == "POTENTIAL_ISSUE"
                for issue in issues
            )
        )

        self.assertTrue(
            result[
                "review_units"
            ][0]["qa_issue_ids"]
        )

    def test_approved_target_is_rejected(
        self,
    ):
        value = proposal(
            source="配置主库",
            suggested=(
                "Configure the primary database."
            ),
        )

        value["units"][0][
            "approved_target"
        ] = "forbidden"

        with self.assertRaises(
            PostTranslationError
        ):
            prepare_post_translation(
                value,
                source_language="zh-CN",
                target_language="en",
            )


if __name__ == "__main__":
    unittest.main()

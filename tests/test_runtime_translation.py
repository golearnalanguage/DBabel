import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from providers.base import ProviderResponseInterrupted

from runtime.models import (
    GenerationResponse,
)
from runtime.translation import (
    RuntimeTranslationError,
    TranslationLimits,
    batch_units,
    parse_batch_response,
    protected_literals,
    translate_units,
)


def unit(
    unit_id,
    source,
    role="PROSE",
):
    return {
        "id": unit_id,
        "location": "line:1",
        "source": source,
        "target": "",
        "source_language": "zh-CN",
        "target_language": "en",
        "alignment": "ALIGNED",
        "context": {
            "text_role": role,
        },
    }


class FakeProvider:
    def __init__(self, responses):
        self.responses = list(
            responses
        )
        self.requests = []

    def generate(self, request):
        self.requests.append(request)

        if not self.responses:
            raise AssertionError(
                "unexpected provider call"
            )

        text = self.responses.pop(0)

        return GenerationResponse(
            text=text,
            model="fake-model",
            provider="fake-provider",
            response_id="fake-response",
            usage={
                "total_tokens": 10,
            },
        )


class TranslationRuntimeTests(
    unittest.TestCase
):
    def test_literal_count_is_retried_for_single_unit(self):
        source = "先设置 --exec_mode，再检查 --exec_mode。"
        def answer(target):
            return json.dumps({"units": [{
                "id": "U1", "suggested_target": target,
                "proposal_decision": "REPLACE", "reason": "technical translation"
            }]})
        provider = FakeProvider([
            answer("Set --exec_mode first, then check the option."),
            answer("Set --exec_mode first, then check --exec_mode."),
        ])
        result = translate_units(provider=provider, units=[unit("U1", source)],
                                 source_language="zh-CN", target_language="en")
        self.assertEqual(len(provider.requests), 2)
        self.assertEqual(result["units"][0]["proposal_decision"], "REPLACE")
        self.assertEqual(result["units"][0]["suggested_target"].count("--exec_mode"), 2)
        self.assertIn("protected_literal_counts", provider.requests[0].user)
        self.assertIn("Previous response changed", provider.requests[1].user)

    def test_rejected_translation_is_retried_and_cannot_recur(self):
        with tempfile.TemporaryDirectory() as directory:
            memory = Path(directory) / "rejected.json"
            memory.write_text(json.dumps([{
                "source": "配置主库", "source_language": "zh-CN",
                "target_language": "en", "rejected_target": "Configure the primary database."
            }]), encoding="utf-8")
            def answer(target):
                return json.dumps({"units": [{"id": "U1", "suggested_target": target,
                    "proposal_decision": "REPLACE", "reason": "technical wording"}]})
            provider = FakeProvider([answer("Configure the primary database."),
                                     answer("Set up the primary database.")])
            with patch.dict(os.environ, {"DBABEL_REJECTION_MEMORY": str(memory)}):
                result = translate_units(provider=provider, units=[unit("U1", "配置主库")],
                                         source_language="zh-CN", target_language="en")
            self.assertEqual(result["units"][0]["suggested_target"], "Set up the primary database.")
            self.assertEqual(len(provider.requests), 2)
            self.assertIn("Configure the primary database.", provider.requests[0].user)

    def test_rejected_translation_fails_closed_after_retries(self):
        with tempfile.TemporaryDirectory() as directory:
            memory = Path(directory) / "rejected.json"
            memory.write_text(json.dumps([{
                "source": "配置主库", "source_language": "zh-CN",
                "target_language": "en", "rejected_target": "Configure the primary database."
            }]), encoding="utf-8")
            answer = json.dumps({"units": [{"id": "U1", "suggested_target": "Configure the primary database.",
                "proposal_decision": "REPLACE", "reason": "technical wording"}]})
            with patch.dict(os.environ, {"DBABEL_REJECTION_MEMORY": str(memory)}):
                with self.assertRaisesRegex(RuntimeTranslationError, "repeated a rejected translation"):
                    translate_units(provider=FakeProvider([answer] * 3), units=[unit("U1", "配置主库")],
                                    source_language="zh-CN", target_language="en")

    def test_rejected_term_is_blocked_inside_later_sentence(self):
        with tempfile.TemporaryDirectory() as directory:
            memory = Path(directory) / "rejected.json"
            memory.write_text(json.dumps([{
                "source": "主库", "source_language": "zh-CN", "target_language": "en",
                "rejected_target": "primary database", "scope": "TERM"
            }]), encoding="utf-8")
            def answer(target):
                return json.dumps({"units": [{"id": "U1", "suggested_target": target,
                    "proposal_decision": "REPLACE", "reason": "technical wording"}]})
            provider = FakeProvider([answer("Configure the primary database."),
                                     answer("Configure the primary instance.")])
            with patch.dict(os.environ, {"DBABEL_REJECTION_MEMORY": str(memory)}):
                result = translate_units(provider=provider, units=[unit("U1", "配置主库")],
                                         source_language="zh-CN", target_language="en")
            self.assertEqual(result["units"][0]["suggested_target"], "Configure the primary instance.")
            self.assertIn("rejected_phrases", provider.requests[0].user)

    def test_persistent_literal_mismatch_is_review_only(self):
        source = "检查 SELECT * FROM V$DATABASE 的结果。"
        response = json.dumps({"units": [{
            "id": "U1", "suggested_target": "Check the database query result.",
            "proposal_decision": "REPLACE", "reason": "technical translation"
        }]})
        provider = FakeProvider([response] * 3)
        result = translate_units(provider=provider, units=[unit("U1", source)],
                                 source_language="zh-CN", target_language="en")
        proposal = result["units"][0]
        self.assertEqual(len(provider.requests), 3)
        self.assertEqual(proposal["proposal_decision"], "REVIEW")
        self.assertIn("V$DATABASE", proposal["suggestion_reason"])
        self.assertNotIn("approved_target", proposal)

    def test_progress_reports_units_after_batch_succeeds(self):
        response = json.dumps({"units": [{
            "id": "U1", "suggested_target": "Configure the primary database.",
            "proposal_decision": "REPLACE", "reason": "Translated instruction"
        }]})
        events = []
        translate_units(provider=FakeProvider([response]),
                        units=[unit("U1", "配置主库")],
                        source_language="zh-CN", target_language="en",
                        on_progress=events.append)
        self.assertEqual([event["state"] for event in events],
                         ["BATCH_STARTED", "BATCH_COMPLETED"])
        self.assertEqual(events[-1]["completed_units"], 1)
        self.assertEqual(events[0]["source_preview"], "配置主库")

    def test_batching_enforces_unit_and_character_limits(
        self,
    ):
        units = [
            unit("U1", "a" * 100),
            unit("U2", "b" * 100),
            unit("U3", "c" * 100),
        ]

        batches = batch_units(
            units,
            TranslationLimits(
                max_units_per_batch=2,
                max_source_chars_per_batch=256,
            ),
        )

        self.assertEqual(
            [
                [x["id"] for x in batch]
                for batch in batches
            ],
            [
                ["U1", "U2"],
                ["U3"],
            ],
        )

    def test_response_ids_must_match_exactly_and_in_order(
        self,
    ):
        batch = [
            unit("U1", "配置主库"),
            unit("U2", "启动服务"),
        ]

        response = json.dumps({
            "units": [
                {
                    "id": "U2",
                    "suggested_target":
                        "Start the service.",
                    "proposal_decision":
                        "REPLACE",
                    "reason": "translation",
                },
                {
                    "id": "U1",
                    "suggested_target":
                        "Configure the primary database.",
                    "proposal_decision":
                        "REPLACE",
                    "reason": "translation",
                },
            ]
        })

        with self.assertRaises(
            RuntimeTranslationError
        ):
            parse_batch_response(
                response,
                batch,
            )

    def test_human_approval_fields_are_rejected(
        self,
    ):
        batch = [
            unit("U1", "配置主库"),
        ]

        response = json.dumps({
            "units": [{
                "id": "U1",
                "suggested_target":
                    "Configure the primary database.",
                "proposal_decision":
                    "REPLACE",
                "reason": "translation",
                "approved_target":
                    "Configure the primary database.",
            }]
        })

        with self.assertRaises(
            RuntimeTranslationError
        ):
            parse_batch_response(
                response,
                batch,
            )

    def test_protected_literal_mutation_fails_closed(
        self,
    ):
        batch = [
            unit(
                "U1",
                "编辑 /opt/example/config.ini 后启动服务。",
            ),
        ]

        response = json.dumps({
            "units": [{
                "id": "U1",
                "suggested_target":
                    "Edit /opt/example/config-en.ini "
                    "and start the service.",
                "proposal_decision":
                    "REPLACE",
                "reason": "translation",
            }]
        })

        with self.assertRaises(
            RuntimeTranslationError
        ):
            parse_batch_response(
                response,
                batch,
            )

    def test_existing_literal_extractors_are_reused(
        self,
    ):
        text = (
            "Use --force with "
            "/opt/example/config.ini and "
            "${DB_HOME} at version 8.1."
        )

        values = protected_literals(
            text
        )

        self.assertIn(
            "--force",
            values,
        )

        self.assertIn(
            "/opt/example/config.ini",
            values,
        )

        self.assertIn(
            "${DB_HOME}",
            values,
        )

        self.assertIn(
            "8.1",
            values,
        )

    def test_workflow_words_are_not_protected_as_a_path(self):
        text = "“材料输入→文本/结构抽取→人工确认”"
        self.assertEqual(protected_literals(text), [])
        self.assertIn("ARCH_MODE", protected_literals("参数 ARCH_MODE"))
        self.assertIn("V$DATABASE", protected_literals("SELECT * FROM V$DATABASE"))

    def test_transient_failure_splits_batch_and_keeps_unit_order(self):
        class SplittingProvider:
            def generate(self, request):
                ids = [item["id"] for item in json.loads(request.user)["units"]]
                if len(ids) > 1:
                    raise ProviderResponseInterrupted("truncated response")
                return GenerationResponse(
                    text=json.dumps({"units": [{
                        "id": ids[0], "suggested_target": "Translated " + ids[0],
                        "proposal_decision": "REPLACE", "reason": "translated"
                    }]}), model="fake", provider="fake", response_id=None, usage={})

        result = translate_units(
            provider=SplittingProvider(),
            units=[unit("U1", "第一句"), unit("U2", "第二句")],
            source_language="zh-CN", target_language="en")
        self.assertEqual(result["batch_count"], 2)
        self.assertEqual([x["id"] for x in result["units"]], ["U1", "U2"])

    def test_success_is_proposal_only(
        self,
    ):
        units = [
            unit(
                "U1",
                "配置主库",
            ),
            unit(
                "U2",
                "编辑 /opt/example/config.ini。",
            ),
        ]

        provider = FakeProvider([
            json.dumps({
                "units": [
                    {
                        "id": "U1",
                        "suggested_target":
                            "Configure the primary database.",
                        "proposal_decision":
                            "REPLACE",
                        "reason":
                            "technical translation",
                    },
                    {
                        "id": "U2",
                        "suggested_target":
                            "Edit /opt/example/config.ini.",
                        "proposal_decision":
                            "REPLACE",
                        "reason":
                            "technical translation",
                    },
                ]
            })
        ])

        result = translate_units(
            provider=provider,
            units=units,
            source_language="zh-CN",
            target_language="en",
        )

        self.assertEqual(
            result["status"],
            "TRANSLATION_PROPOSED",
        )

        self.assertFalse(
            result[
                "completion_allowed"
            ]
        )

        self.assertEqual(
            result["unit_count"],
            2,
        )

        self.assertTrue(
            result["receipts"]
        )

        for translated in result["units"]:
            self.assertEqual(
                translated["target"],
                "",
            )

            self.assertIn(
                "suggested_target",
                translated,
            )

            self.assertNotIn(
                "approved_target",
                translated,
            )


if __name__ == "__main__":
    unittest.main()

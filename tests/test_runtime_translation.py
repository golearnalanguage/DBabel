import json
import unittest

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

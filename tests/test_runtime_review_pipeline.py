import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(
    __file__
).resolve().parents[1]

SCRIPTS = ROOT / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(
        0,
        str(SCRIPTS),
    )

from review_model import (
    load_bundle,
)

from runtime.audit import (
    read_events,
    verify_file,
)
from runtime.models import (
    GenerationResponse,
)
from runtime.orchestrator import (
    OrchestrationError,
    RuntimeOrchestrator,
)


class UnifiedProvider:
    def __init__(
        self,
        *,
        bad_semantic=False,
    ):
        self.bad_semantic = (
            bad_semantic
        )

    def generate(
        self,
        request,
    ):
        payload = json.loads(
            request.user
        )

        task = payload.get(
            "task"
        )

        if (
            task
            == "DBabel bounded technical translation proposal"
        ):
            rows = []

            for unit in payload[
                "units"
            ]:
                if (
                    unit["source"]
                    == "配置主库"
                ):
                    suggested = (
                        "Configure the primary database."
                    )
                else:
                    raise AssertionError(
                        "unexpected translation source"
                    )

                rows.append({
                    "id":
                        unit["id"],
                    "suggested_target":
                        suggested,
                    "proposal_decision":
                        "REPLACE",
                    "reason":
                        "fake integrated translation",
                })

            text = json.dumps(
                {
                    "units": rows,
                },
                ensure_ascii=False,
            )

        elif (
            task
            == "DBabel semantic risk adjudication"
        ):
            rows = []

            for unit in payload[
                "units"
            ]:
                if self.bad_semantic:
                    rows.append({
                        "id":
                            unit["id"],
                        "outcome":
                            "REPLACE",
                        "classification":
                            "VENDOR_CONCEPT",
                        "reason":
                            "forbidden semantic replacement",
                        "next_action":
                            "replace",
                    })
                else:
                    rows.append({
                        "id":
                            unit["id"],
                        "outcome":
                            "NO_FINDING",
                        "classification":
                            None,
                        "reason":
                            "No additional semantic risk surfaced.",
                        "next_action":
                            "",
                    })

            text = json.dumps(
                {
                    "units": rows,
                },
                ensure_ascii=False,
            )

        else:
            raise AssertionError(
                "unexpected provider task: {!r}".format(
                    task
                )
            )

        return GenerationResponse(
            text=text,
            model="fake-integrated-model",
            provider="fake-provider",
            response_id="fake-integrated-response",
            usage={
                "total_tokens": 20,
            },
        )


class RuntimeReviewPipelineTests(
    unittest.TestCase
):
    def provider_config(
        self,
        root: Path,
    ) -> Path:
        path = (
            root
            / "provider.json"
        )

        path.write_text(
            json.dumps({
                "provider":
                    "openai-compatible",
                "base_url":
                    "https://example.com/v1",
                "api_key_env":
                    "DBABEL_TEST_KEY",
                "model":
                    "model-a",
                "timeout_seconds":
                    120,
                "max_response_bytes":
                    2000000,
            }),
            encoding="utf-8",
        )

        return path

    def test_complete_runtime_reaches_full_human_review_gate(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            source = (
                root
                / "source.txt"
            )

            original = (
                "配置主库\n"
            ).encode("utf-8")

            source.write_bytes(
                original
            )

            workspace = (
                root / "runs"
            )

            result = (
                RuntimeOrchestrator(
                    workspace_root=
                        workspace,
                ).run_translation_to_review(
                    source=source,
                    source_language=
                        "zh-CN",
                    target_language=
                        "en",
                    provider_config_path=
                        self.provider_config(
                            root
                        ),
                    default_text_role=
                        "PROSE",
                    provider=
                        UnifiedProvider(),
                )
            )

            self.assertEqual(
                result["status"],
                "READY_FOR_HUMAN_REVIEW",
            )

            self.assertEqual(
                result[
                    "current_stage"
                ],
                "DELIVERY_VALIDATION",
            )

            self.assertFalse(
                result[
                    "completion_allowed"
                ]
            )

            self.assertEqual(
                source.read_bytes(),
                original,
            )

            bundle = Path(
                result[
                    "artifacts"
                ][
                    "review_bundle"
                ][
                    "path"
                ]
            )

            self.assertTrue(
                bundle.is_dir()
            )

            data = load_bundle(
                bundle
            )

            unit = data[
                "units"
            ][0]

            self.assertEqual(
                unit[
                    "current_target"
                ],
                "配置主库",
            )

            self.assertEqual(
                unit[
                    "suggested_target"
                ],
                "Configure the primary database.",
            )

            self.assertNotIn(
                "approved_target",
                unit,
            )

            self.assertEqual(
                data[
                    "decisions"
                ][0]["status"],
                "UNREVIEWED",
            )

            receipt = json.loads(
                Path(
                    result[
                        "artifacts"
                    ][
                        "delivery_receipt"
                    ][
                        "path"
                    ]
                ).read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(
                receipt["status"],
                "READY_FOR_HUMAN_REVIEW",
            )

            self.assertEqual(
                receipt["surface"],
                "FULL_LOCAL_WORKBENCH_READY",
            )

            self.assertFalse(
                receipt[
                    "completion_allowed"
                ]
            )

            audit_path = (
                workspace
                / result["run_id"]
                / "audit.jsonl"
            )

            verification = (
                verify_file(
                    audit_path,
                    expected_run_id=
                        result["run_id"],
                )
            )

            self.assertTrue(
                verification[
                    "valid"
                ]
            )

            pairs = [
                (
                    event["stage"],
                    event["status"],
                )
                for event
                in read_events(
                    audit_path
                )
            ]

            for expected in (
                (
                    "ADJUDICATION",
                    "PASS",
                ),
                (
                    "REVIEW_SESSION_BINDING",
                    "PASS",
                ),
                (
                    "DELIVERY_VALIDATION",
                    "PASS",
                ),
                (
                    "HUMAN_REVIEW",
                    "READY",
                ),
            ):
                self.assertIn(
                    expected,
                    pairs,
                )

    def test_bad_semantic_output_fails_before_review_bundle(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            source = (
                root
                / "source.txt"
            )

            original = (
                "配置主库\n"
            ).encode("utf-8")

            source.write_bytes(
                original
            )

            workspace = (
                root / "runs"
            )

            orchestrator = (
                RuntimeOrchestrator(
                    workspace_root=
                        workspace,
                )
            )

            with self.assertRaises(
                OrchestrationError
            ):
                orchestrator.run_translation_to_review(
                    source=source,
                    source_language=
                        "zh-CN",
                    target_language=
                        "en",
                    provider_config_path=
                        self.provider_config(
                            root
                        ),
                    default_text_role=
                        "PROSE",
                    provider=
                        UnifiedProvider(
                            bad_semantic=True
                        ),
                )

            runs = list(
                workspace.glob(
                    "RUN_*"
                )
            )

            self.assertEqual(
                len(runs),
                1,
            )

            manifest = json.loads(
                (
                    runs[0]
                    / "run.json"
                ).read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(
                manifest[
                    "status"
                ],
                "FAILED",
            )

            self.assertEqual(
                manifest[
                    "current_stage"
                ],
                "ADJUDICATION",
            )

            self.assertFalse(
                (
                    runs[0]
                    / "review.dbreview"
                ).exists()
            )

            self.assertEqual(
                source.read_bytes(),
                original,
            )

            self.assertTrue(
                verify_file(
                    runs[0]
                    / "audit.jsonl",
                    expected_run_id=
                        manifest[
                            "run_id"
                        ],
                )["valid"]
            )


if __name__ == "__main__":
    unittest.main()

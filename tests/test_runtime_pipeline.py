import json
import tempfile
import unittest
from pathlib import Path

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
from runtime.project import (
    sha256_file,
)


class FakeProvider:
    def __init__(
        self,
        *,
        bad_id=False,
    ):
        self.bad_id = bad_id

    def generate(self, request):
        payload = json.loads(
            request.user
        )

        units = []

        mapping = {
            "配置主库":
                "Configure the primary database.",
            "端口为 5236。":
                "The port is 5236.",
        }

        for index, unit in enumerate(
            payload["units"]
        ):
            unit_id = unit["id"]

            if (
                self.bad_id
                and index == 0
            ):
                unit_id = "WRONG_ID"

            units.append({
                "id": unit_id,
                "suggested_target":
                    mapping[
                        unit["source"]
                    ],
                "proposal_decision":
                    "REPLACE",
                "reason":
                    "fake pipeline translation",
            })

        return GenerationResponse(
            text=json.dumps(
                {
                    "units": units,
                },
                ensure_ascii=False,
            ),
            model="fake-model",
            provider="fake-provider",
            response_id="fake-response",
            usage={
                "total_tokens": 20,
            },
        )


class RuntimePipelineTests(
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

    def test_pipeline_reaches_semantic_adjudication_without_approval(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            source = (
                root / "source.txt"
            )

            original = (
                "配置主库\n"
                "端口为 5236。\n"
            ).encode("utf-8")

            source.write_bytes(
                original
            )

            workspace = (
                root / "runs"
            )

            manifest = (
                RuntimeOrchestrator(
                    workspace_root=
                        workspace,
                ).run_translation_to_qa(
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
                        FakeProvider(),
                )
            )

            self.assertEqual(
                manifest["status"],
                "READY_FOR_SEMANTIC_ADJUDICATION",
            )

            self.assertEqual(
                manifest[
                    "current_stage"
                ],
                "POST_TRANSLATION_QA",
            )

            self.assertFalse(
                manifest[
                    "completion_allowed"
                ]
            )

            self.assertEqual(
                source.read_bytes(),
                original,
            )

            artifacts = (
                manifest["artifacts"]
            )

            for key in (
                "runtime_plan",
                "ingest",
                "translation_proposals",
                "post_translation",
            ):
                record = artifacts[key]
                path = Path(
                    record["path"]
                )

                self.assertTrue(
                    path.is_file()
                )

                self.assertEqual(
                    sha256_file(path),
                    record["sha256"],
                )

            translation = json.loads(
                Path(
                    artifacts[
                        "translation_proposals"
                    ]["path"]
                ).read_text(
                    encoding="utf-8"
                )
            )

            for unit in translation[
                "units"
            ]:
                self.assertEqual(
                    unit["target"],
                    "",
                )

                self.assertIn(
                    "suggested_target",
                    unit,
                )

                self.assertNotIn(
                    "approved_target",
                    unit,
                )

            post = json.loads(
                Path(
                    artifacts[
                        "post_translation"
                    ]["path"]
                ).read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(
                post[
                    "translation_review_intake"
                ]["phase"],
                "POST_TRANSLATION",
            )

            self.assertEqual(
                post["handoff"]["status"],
                "READY_FOR_SEMANTIC_ADJUDICATION",
            )

            audit_path = (
                workspace
                / manifest["run_id"]
                / "audit.jsonl"
            )

            verification = (
                verify_file(
                    audit_path,
                    expected_run_id=
                        manifest["run_id"],
                )
            )

            self.assertTrue(
                verification["valid"]
            )

            events = read_events(
                audit_path
            )

            pairs = [
                (
                    event["stage"],
                    event["status"],
                )
                for event in events
            ]

            self.assertIn(
                (
                    "INGEST",
                    "PASS",
                ),
                pairs,
            )

            self.assertIn(
                (
                    "TRANSLATION",
                    "PASS",
                ),
                pairs,
            )

            self.assertIn(
                (
                    "POST_TRANSLATION_QA",
                    "PASS",
                ),
                pairs,
            )

            self.assertIn(
                (
                    "SEMANTIC_ADJUDICATION",
                    "READY",
                ),
                pairs,
            )

    def test_bad_provider_output_marks_run_failed(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            source = (
                root / "source.txt"
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
                orchestrator.run_translation_to_qa(
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
                        FakeProvider(
                            bad_id=True
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
                manifest["status"],
                "FAILED",
            )

            self.assertEqual(
                manifest[
                    "current_stage"
                ],
                "TRANSLATION",
            )

            self.assertEqual(
                source.read_bytes(),
                original,
            )

            verification = (
                verify_file(
                    runs[0]
                    / "audit.jsonl",
                    expected_run_id=
                        manifest["run_id"],
                )
            )

            self.assertTrue(
                verification["valid"]
            )

            events = read_events(
                runs[0]
                / "audit.jsonl"
            )

            self.assertEqual(
                events[-1]["stage"],
                "TRANSLATION",
            )

            self.assertEqual(
                events[-1]["status"],
                "FAILED",
            )


if __name__ == "__main__":
    unittest.main()

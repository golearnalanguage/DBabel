import json
import tempfile
import unittest
from pathlib import Path

from runtime.audit import (
    AuditError,
    AuditTrail,
    read_events,
    verify_file,
)
from runtime.orchestrator import (
    RuntimeOrchestrator,
)


class AuditTrailTests(unittest.TestCase):
    def test_hash_chain_verifies_and_detects_tamper(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "audit.jsonl"

            trail = AuditTrail(
                path,
                "RUN_TEST",
            )

            trail.append(
                stage="INTAKE",
                status="CREATED",
                details={"value": 1},
            )

            trail.append(
                stage="FORMAT_PROBE",
                status="PASS",
                details={"value": 2},
            )

            result = verify_file(
                path,
                expected_run_id="RUN_TEST",
            )

            self.assertEqual(
                result["event_count"],
                2,
            )

            events = read_events(path)
            events[0]["details"]["value"] = 9

            path.write_text(
                "\n".join(
                    json.dumps(x)
                    for x in events
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaises(
                AuditError
            ):
                verify_file(
                    path,
                    expected_run_id="RUN_TEST",
                )

    def test_sensitive_details_are_redacted(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "audit.jsonl"

            AuditTrail(
                path,
                "RUN_TEST",
            ).append(
                stage="TEST",
                status="PASS",
                details={
                    "api_key": "secret-value",
                    "nested": {
                        "authorization":
                            "Bearer secret"
                    },
                },
            )

            text = path.read_text(
                encoding="utf-8"
            )

            self.assertNotIn(
                "secret-value",
                text,
            )

            self.assertNotIn(
                "Bearer secret",
                text,
            )

            self.assertIn(
                "<redacted>",
                text,
            )


class RuntimeOrchestratorTests(
    unittest.TestCase
):
    def provider_config(
        self,
        root: Path,
    ) -> Path:
        path = root / "provider.json"

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

    def test_prepare_translation_is_traceable_and_non_mutating(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source.txt"

            original = (
                "第一行\n第二行\n"
            ).encode("utf-8")

            source.write_bytes(original)

            workspace = root / "runs"

            manifest = RuntimeOrchestrator(
                workspace_root=workspace,
            ).prepare_translation(
                source=source,
                source_language="zh-CN",
                target_language="en",
                provider_config_path=
                    self.provider_config(root),
            )

            self.assertEqual(
                manifest["status"],
                "READY_FOR_INGEST",
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

            run_root = Path(
                manifest["artifacts"]
                ["runtime_plan"]
                ["path"]
            ).parent

            audit_path = (
                run_root
                / "audit.jsonl"
            )

            verification = verify_file(
                audit_path,
                expected_run_id=
                    manifest["run_id"],
            )

            self.assertGreaterEqual(
                verification[
                    "event_count"
                ],
                5,
            )

            run_text = (
                run_root
                / "run.json"
            ).read_text(
                encoding="utf-8"
            )

            self.assertNotIn(
                "DBABEL_TEST_KEY=",
                run_text,
            )

            self.assertNotIn(
                "secret-value",
                run_text,
            )

    def test_same_language_translation_fails_before_run_creation(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source.txt"
            source.write_text(
                "hello\n",
                encoding="utf-8",
            )

            workspace = root / "runs"

            with self.assertRaises(
                ValueError
            ):
                RuntimeOrchestrator(
                    workspace_root=workspace,
                ).prepare_translation(
                    source=source,
                    source_language="en",
                    target_language="en",
                    provider_config_path=
                        self.provider_config(root),
                )

            self.assertFalse(
                workspace.exists()
            )


if __name__ == "__main__":
    unittest.main()

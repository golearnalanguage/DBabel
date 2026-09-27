import io
import json
import sys
import tempfile
import unittest
from contextlib import (
    redirect_stderr,
    redirect_stdout,
)
from pathlib import Path
from unittest.mock import (
    MagicMock,
    patch,
)

from scripts import run_project


class RuntimeCliTests(
    unittest.TestCase
):
    def manifest(
        self,
        bundle: Path,
    ):
        return {
            "run_id": "RUN_test",
            "status":
                "READY_FOR_HUMAN_REVIEW",
            "current_stage":
                "DELIVERY_VALIDATION",
            "completion_allowed":
                False,
            "artifacts": {
                "review_bundle": {
                    "path":
                        str(bundle),
                }
            },
        }

    def test_cli_runs_complete_pipeline(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            source = (
                root / "source.txt"
            )
            source.write_text(
                "配置主库\n",
                encoding="utf-8",
            )

            provider = (
                root / "provider.json"
            )
            provider.write_text(
                "{}",
                encoding="utf-8",
            )

            bundle = (
                root / "review.dbreview"
            )
            bundle.mkdir()

            orchestrator = MagicMock()

            orchestrator.run_translation_to_review.return_value = (
                self.manifest(
                    bundle
                )
            )

            argv = [
                "run_project.py",
                str(source),
                "--source-language",
                "zh-CN",
                "--target-language",
                "en",
                "--text-role",
                "PROSE",
                "--provider-config",
                str(provider),
            ]

            stdout = io.StringIO()
            stderr = io.StringIO()

            with patch.object(
                sys,
                "argv",
                argv,
            ):
                with patch.object(
                    run_project,
                    "RuntimeOrchestrator",
                    return_value=
                        orchestrator,
                ):
                    with redirect_stdout(
                        stdout
                    ):
                        with redirect_stderr(
                            stderr
                        ):
                            code = (
                                run_project.main()
                            )

            self.assertEqual(
                code,
                0,
            )

            payload = json.loads(
                stdout.getvalue()
            )

            self.assertEqual(
                payload["status"],
                "READY_FOR_HUMAN_REVIEW",
            )

            call = (
                orchestrator
                .run_translation_to_review
                .call_args
            )

            self.assertEqual(
                call.kwargs[
                    "default_text_role"
                ],
                "PROSE",
            )

            self.assertIn(
                "start_local.py",
                stderr.getvalue(),
            )

    def test_open_workbench_uses_generated_bundle(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            source = (
                root / "source.txt"
            )
            source.write_text(
                "配置主库\n",
                encoding="utf-8",
            )

            provider = (
                root / "provider.json"
            )
            provider.write_text(
                "{}",
                encoding="utf-8",
            )

            bundle = (
                root / "review.dbreview"
            )
            bundle.mkdir()

            orchestrator = MagicMock()

            orchestrator.run_translation_to_review.return_value = (
                self.manifest(
                    bundle
                )
            )

            argv = [
                "run_project.py",
                str(source),
                "--source-language",
                "zh-CN",
                "--target-language",
                "en",
                "--text-role",
                "PROSE",
                "--provider-config",
                str(provider),
                "--open-workbench",
                "--no-browser",
                "--workbench-port",
                "9876",
            ]

            stdout = io.StringIO()
            stderr = io.StringIO()

            with patch.object(
                sys,
                "argv",
                argv,
            ):
                with patch.object(
                    run_project,
                    "RuntimeOrchestrator",
                    return_value=
                        orchestrator,
                ):
                    with patch.object(
                        run_project.subprocess,
                        "call",
                        return_value=0,
                    ) as process:
                        with redirect_stdout(
                            stdout
                        ):
                            with redirect_stderr(
                                stderr
                            ):
                                code = (
                                    run_project.main()
                                )

            self.assertEqual(
                code,
                0,
            )

            command = (
                process.call_args
                .args[0]
            )

            self.assertIn(
                str(bundle.resolve()),
                command,
            )

            self.assertIn(
                "--no-browser",
                command,
            )

            self.assertEqual(
                command[
                    command.index(
                        "--port"
                    )
                    + 1
                ],
                "9876",
            )

            self.assertEqual(
                command[
                    command.index(
                        "--original"
                    )
                    + 1
                ],
                str(
                    source.resolve()
                ),
            )

            self.assertEqual(
                command[
                    command.index(
                        "--output"
                    )
                    + 1
                ],
                str(
                    (
                        bundle.parent
                        / "reviewed-source.txt"
                    ).resolve()
                ),
            )

    def test_blocked_run_returns_one_without_workbench(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            source = (
                root / "source.txt"
            )
            source.write_text(
                "配置主库\n",
                encoding="utf-8",
            )

            provider = (
                root / "provider.json"
            )
            provider.write_text(
                "{}",
                encoding="utf-8",
            )

            orchestrator = MagicMock()

            orchestrator.run_translation_to_review.return_value = {
                "run_id":
                    "RUN_blocked",
                "status":
                    "BLOCKED",
                "completion_allowed":
                    False,
                "artifacts": {},
            }

            argv = [
                "run_project.py",
                str(source),
                "--source-language",
                "zh-CN",
                "--target-language",
                "en",
                "--text-role",
                "PROSE",
                "--provider-config",
                str(provider),
            ]

            stdout = io.StringIO()
            stderr = io.StringIO()

            with patch.object(
                sys,
                "argv",
                argv,
            ):
                with patch.object(
                    run_project,
                    "RuntimeOrchestrator",
                    return_value=
                        orchestrator,
                ):
                    with patch.object(
                        run_project.subprocess,
                        "call",
                    ) as process:
                        with redirect_stdout(
                            stdout
                        ):
                            with redirect_stderr(
                                stderr
                            ):
                                code = (
                                    run_project.main()
                                )

            self.assertEqual(
                code,
                1,
            )

            process.assert_not_called()


if __name__ == "__main__":
    unittest.main()

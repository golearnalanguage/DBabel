import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import start_local


class StartLocalTests(unittest.TestCase):
    def test_native_export_arguments_are_forwarded(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            bundle = root / "review.dbreview"
            bundle.mkdir()

            original = root / "source.txt"
            original.write_text(
                "配置主库\n",
                encoding="utf-8",
            )

            output = root / "reviewed-source.txt"

            argv = [
                "start_local.py",
                "--bundle",
                str(bundle),
                "--original",
                str(original),
                "--output",
                str(output),
                "--port",
                "0",
                "--no-browser",
            ]

            with patch.object(
                sys,
                "argv",
                argv,
            ):
                with patch.object(
                    start_local.subprocess,
                    "call",
                    return_value=0,
                ) as process:
                    code = start_local.main()

            self.assertEqual(
                code,
                0,
            )

            command = (
                process.call_args.args[0]
            )

            self.assertEqual(
                command[
                    command.index(
                        "--original"
                    )
                    + 1
                ],
                str(original.resolve()),
            )

            self.assertEqual(
                command[
                    command.index(
                        "--output"
                    )
                    + 1
                ],
                str(output.resolve()),
            )

            self.assertEqual(
                command[
                    command.index(
                        "--port"
                    )
                    + 1
                ],
                "0",
            )

            self.assertIn(
                "--no-browser",
                command,
            )

    def test_original_and_output_must_be_paired(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            bundle = root / "review.dbreview"
            bundle.mkdir()

            original = root / "source.txt"
            original.write_text(
                "配置主库\n",
                encoding="utf-8",
            )

            argv = [
                "start_local.py",
                "--bundle",
                str(bundle),
                "--original",
                str(original),
            ]

            with patch.object(
                sys,
                "argv",
                argv,
            ):
                with self.assertRaises(
                    SystemExit
                ) as raised:
                    start_local.main()

            self.assertEqual(
                raised.exception.code,
                2,
            )

    def test_output_cannot_overwrite_original(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)

            bundle = root / "review.dbreview"
            bundle.mkdir()

            original = root / "source.txt"
            original.write_text(
                "配置主库\n",
                encoding="utf-8",
            )

            argv = [
                "start_local.py",
                "--bundle",
                str(bundle),
                "--original",
                str(original),
                "--output",
                str(original),
            ]

            with patch.object(
                sys,
                "argv",
                argv,
            ):
                with self.assertRaises(
                    SystemExit
                ) as raised:
                    start_local.main()

            self.assertEqual(
                raised.exception.code,
                2,
            )


if __name__ == "__main__":
    unittest.main()

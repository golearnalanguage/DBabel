import tempfile
import unittest
from pathlib import Path

from runtime.ingest import (
    RuntimeIngestError,
    ingest_for_translation,
)
from validate_ingest import (
    validate_ingest_report,
)


class RuntimeIngestTests(
    unittest.TestCase
):
    def test_txt_ingest_builds_stable_pretranslation_units(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source.txt"

            original = (
                "配置主库\n"
                "启动数据库服务\n"
                "检查归档状态\n"
            ).encode("utf-8")

            source.write_bytes(
                original
            )

            result = ingest_for_translation(
                source=source,
                source_language="zh-CN",
                target_language="en",
                backend="builtin_text",
                default_text_role="PROSE",
            )

            self.assertEqual(
                source.read_bytes(),
                original,
            )

            self.assertEqual(
                [
                    unit["id"]
                    for unit in result["units"]
                ],
                [
                    "U00001_en",
                    "U00002_en",
                    "U00003_en",
                ],
            )

            self.assertEqual(
                [
                    unit["location"]
                    for unit in result["units"]
                ],
                [
                    "line:1",
                    "line:2",
                    "line:3",
                ],
            )

            self.assertTrue(
                all(
                    unit["target"] == ""
                    for unit in result["units"]
                )
            )

            intake = result[
                "pre_translation_intake"
            ]

            self.assertEqual(
                intake["phase"],
                "PRE_TRANSLATION",
            )

            self.assertEqual(
                intake["handoff"]["status"],
                "READY_FOR_TRANSLATION",
            )

            self.assertEqual(
                intake["handoff"]["next_state"],
                "TRANSLATION",
            )

            self.assertEqual(
                intake["deterministic_qa"]["status"],
                "NOT_RUN",
            )

            self.assertIsNone(
                intake["deterministic_qa"]["report"]
            )

    def test_ingest_report_obeys_existing_contract(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            source = (
                Path(td)
                / "source.txt"
            )

            source.write_text(
                "配置主库\n",
                encoding="utf-8",
            )

            result = ingest_for_translation(
                source=source,
                source_language="zh-CN",
                target_language="en",
                backend="builtin_text",
                default_text_role="PROSE",
            )

            report = result[
                "ingest_report"
            ]

            self.assertEqual(
                validate_ingest_report(
                    report
                ),
                [],
            )

            self.assertEqual(
                report["units_extracted"],
                1,
            )

            self.assertTrue(
                report[
                    "locations_available"
                ]
            )

            # Preserve the extractor's explicit
            # limitations instead of silently
            # upgrading bounded coverage to PASS.
            self.assertEqual(
                report["status"],
                "PARTIAL",
            )

            self.assertTrue(
                report["limitations"]
            )

    def test_same_language_translation_fails_closed(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            source = (
                Path(td)
                / "source.txt"
            )

            source.write_text(
                "hello\n",
                encoding="utf-8",
            )

            with self.assertRaises(
                RuntimeIngestError
            ):
                ingest_for_translation(
                    source=source,
                    source_language="en",
                    target_language="en",
                    backend="builtin_text",
                default_text_role="PROSE",
                )

    def test_invalid_language_tag_fails_closed(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            source = (
                Path(td)
                / "source.txt"
            )

            source.write_text(
                "配置主库\n",
                encoding="utf-8",
            )

            with self.assertRaises(
                RuntimeIngestError
            ):
                ingest_for_translation(
                    source=source,
                    source_language="zh_CN",
                    target_language="en",
                    backend="builtin_text",
                default_text_role="PROSE",
                )

    def test_missing_text_role_fails_closed(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            source = (
                Path(td)
                / "source.txt"
            )

            source.write_text(
                "配置主库\\n",
                encoding="utf-8",
            )

            with self.assertRaises(
                RuntimeIngestError
            ):
                ingest_for_translation(
                    source=source,
                    source_language="zh-CN",
                    target_language="en",
                    backend="builtin_text",
                )

    def test_source_is_not_modified(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            source = (
                Path(td)
                / "source.txt"
            )

            original = (
                "将 /opt/example/config.ini "
                "写入配置文件。\n"
            ).encode("utf-8")

            source.write_bytes(
                original
            )

            ingest_for_translation(
                source=source,
                source_language="zh-CN",
                target_language="en",
                backend="builtin_text",
                default_text_role="PROSE",
            )

            self.assertEqual(
                source.read_bytes(),
                original,
            )


if __name__ == "__main__":
    unittest.main()

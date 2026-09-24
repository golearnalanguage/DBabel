import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from detect_document_format import ProbeError, probe_document
from format_registry import load_registry


class DocumentProbeTests(unittest.TestCase):
    def setUp(self):
        self.registry = load_registry()
        self.temp = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, data):
        path = self.dir / name
        path.write_bytes(data)
        return path

    def make_zip(self, name, members):
        path = self.dir / name
        with zipfile.ZipFile(str(path), "w", compression=zipfile.ZIP_STORED) as zf:
            for member, data in members.items():
                zf.writestr(member, data)
        return path

    def test_pdf_magic(self):
        report = probe_document(self.write("manual.pdf", b"%PDF-1.7\n%%EOF\n"), self.registry, "none")
        self.assertEqual(report["detected_format"], "pdf")
        self.assertEqual(report["status"], "MATCH")
        self.assertEqual(report["confidence"], "HIGH")

    def test_docx_container(self):
        path = self.make_zip(
            "manual.docx",
            {
                "[Content_Types].xml": "<Types/>",
                "word/document.xml": "<w:document/>",
            },
        )
        report = probe_document(path, self.registry, "none")
        self.assertEqual(report["detected_format"], "docx")
        self.assertEqual(report["task_context_format"], "docx")
        self.assertEqual(report["status"], "MATCH")

    def test_docm_macro_container(self):
        path = self.make_zip(
            "manual.docm",
            {
                "[Content_Types].xml": "<Types>macroEnabled</Types>",
                "word/document.xml": "<w:document/>",
                "word/vbaProject.bin": b"synthetic",
            },
        )
        report = probe_document(path, self.registry, "none")
        self.assertEqual(report["detected_format"], "docm")
        self.assertTrue(report["macro_enabled"])
        self.assertIn("MACRO_ENABLED", report["risk_flags"])

    def test_pptx_container(self):
        path = self.make_zip(
            "slides.pptx",
            {"[Content_Types].xml": "<Types/>", "ppt/presentation.xml": "<p:presentation/>"},
        )
        self.assertEqual(probe_document(path, self.registry, "none")["detected_format"], "pptx")

    def test_xlsx_container(self):
        path = self.make_zip(
            "book.xlsx",
            {"[Content_Types].xml": "<Types/>", "xl/workbook.xml": "<workbook/>"},
        )
        report = probe_document(path, self.registry, "none")
        self.assertEqual(report["detected_format"], "xlsx")
        self.assertIn("FORMULA_PRESERVATION", report["risk_flags"])

    def test_odt_mimetype(self):
        path = self.make_zip(
            "note.odt",
            {"mimetype": "application/vnd.oasis.opendocument.text", "content.xml": "<office/>"},
        )
        report = probe_document(path, self.registry, "none")
        self.assertEqual(report["detected_format"], "odt")
        self.assertEqual(report["task_context_format"], "odt")

    def test_epub_mimetype(self):
        path = self.make_zip(
            "book.epub",
            {"mimetype": "application/epub+zip", "META-INF/container.xml": "<container/>"},
        )
        self.assertEqual(probe_document(path, self.registry, "none")["detected_format"], "epub")

    def test_extension_content_conflict(self):
        path = self.make_zip(
            "wrong.pdf",
            {"[Content_Types].xml": "<Types/>", "word/document.xml": "<w:document/>"},
        )
        report = probe_document(path, self.registry, "none")
        self.assertEqual(report["declared_format"], "pdf")
        self.assertEqual(report["detected_format"], "docx")
        self.assertEqual(report["status"], "CONFLICT")
        self.assertIn("EXTENSION_CONTENT_CONFLICT", report["risk_flags"])

    def test_docx_renamed_zip_is_conflict(self):
        path = self.make_zip(
            "manual.zip",
            {"[Content_Types].xml": "<Types/>", "word/document.xml": "<w:document/>"},
        )
        report = probe_document(path, self.registry, "none")
        self.assertEqual(report["detected_format"], "docx")
        self.assertEqual(report["status"], "CONFLICT")

    def test_legacy_ole_uses_extension_only_after_container_verification(self):
        path = self.write("legacy.doc", bytes.fromhex("D0CF11E0A1B11AE1") + b"\x00" * 32)
        report = probe_document(path, self.registry, "none")
        self.assertEqual(report["detected_format"], "ole")
        self.assertEqual(report["effective_format"], "doc")
        self.assertEqual(report["status"], "CONTAINER_MATCH")
        self.assertEqual(report["confidence"], "MEDIUM")

    def test_json(self):
        report = probe_document(self.write("data.json", b'{"a": 1, "b": [2]}'), self.registry, "none")
        self.assertEqual(report["detected_format"], "json")
        self.assertEqual(report["status"], "MATCH")

    def test_html(self):
        report = probe_document(self.write("page.html", b"<!doctype html><html><body>x</body></html>"), self.registry, "none")
        self.assertEqual(report["detected_format"], "html")

    def test_csv(self):
        report = probe_document(self.write("table.csv", b"a,b\n1,2\n3,4\n"), self.registry, "none")
        self.assertEqual(report["detected_format"], "csv")

    def test_markdown(self):
        report = probe_document(self.write("readme.md", b"# Title\n\n- one\n- two\n"), self.registry, "none")
        self.assertEqual(report["detected_format"], "md")

    def test_plain_text(self):
        report = probe_document(self.write("note.txt", b"ordinary sentence without markup\n"), self.registry, "none")
        self.assertEqual(report["detected_format"], "txt")

    def test_unknown_binary_extension_only_is_not_verified(self):
        report = probe_document(self.write("mystery.pdf", b"\x00\x01\x02\x03random"), self.registry, "none")
        self.assertEqual(report["status"], "EXTENSION_ONLY")
        self.assertIn("EXTENSION_ONLY_UNVERIFIED", report["risk_flags"])

    def test_unknown_binary_without_extension(self):
        report = probe_document(self.write("mystery", b"\x00\x01\x02\x03random"), self.registry, "none")
        self.assertEqual(report["status"], "UNKNOWN")
        self.assertEqual(report["effective_format"], "unknown")

    def test_missing_file_rejected(self):
        with self.assertRaises(ProbeError):
            probe_document(self.dir / "missing.docx", self.registry, "none")

    def test_schema_valid_report(self):
        report = probe_document(self.write("manual.pdf", b"%PDF-1.7\n"), self.registry, "none")
        schema = json.loads((ROOT / "schemas/document_probe.schema.json").read_text())
        from jsonschema import Draft202012Validator
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(report)), [])


if __name__ == "__main__":
    unittest.main()

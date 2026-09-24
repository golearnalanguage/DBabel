import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from format_registry import load_registry
from preflight_document import preflight_document, select_backend
from probe_capabilities import probe_capabilities
from route_resources import build_plan, load_router_config


class DocumentPreflightTests(unittest.TestCase):
    def setUp(self):
        self.registry = load_registry()
        self.temp = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def make_docx(self, name="manual.docx", macro=False):
        path = self.dir / name
        with zipfile.ZipFile(str(path), "w", compression=zipfile.ZIP_STORED) as zf:
            zf.writestr("[Content_Types].xml", "<Types>{}</Types>".format("macroEnabled" if macro else ""))
            zf.writestr("word/document.xml", "<w:document/>")
            if macro:
                zf.writestr("word/vbaProject.bin", b"synthetic")
        return path

    def test_docx_selects_declared_python_docx(self):
        report = preflight_document(
            self.make_docx(),
            intent="audit",
            declared_backends=["python_docx"],
            fallback_backend="none",
            registry=self.registry,
        )
        self.assertEqual(report["selection"]["status"], "READY")
        self.assertEqual(report["selection"]["selected_backend"], "python_docx")

    def test_registry_preference_order(self):
        report = preflight_document(
            self.make_docx(),
            intent="audit",
            declared_backends=["docling", "python_docx"],
            fallback_backend="none",
            registry=self.registry,
        )
        self.assertEqual(report["selection"]["selected_backend"], "python_docx")

    def test_content_extension_conflict_blocks_selection(self):
        report = preflight_document(
            self.make_docx("manual.pdf"),
            intent="audit",
            declared_backends=["python_docx", "native_agent"],
            fallback_backend="none",
            registry=self.registry,
        )
        self.assertEqual(report["selection"]["status"], "BLOCKED_FORMAT_CONFLICT")
        self.assertIsNone(report["selection"]["selected_backend"])

    def test_extension_only_blocks_selection(self):
        path = self.dir / "mystery.pdf"
        path.write_bytes(b"\x00\x01broken")
        report = preflight_document(
            path,
            intent="audit",
            declared_backends=["native_agent"],
            fallback_backend="none",
            registry=self.registry,
        )
        self.assertEqual(report["selection"]["status"], "BLOCKED_UNVERIFIED_FORMAT")

    def test_macro_repair_requires_dedicated_workflow(self):
        report = preflight_document(
            self.make_docx("manual.docm", macro=True),
            intent="repair",
            declared_backends=["native_agent", "python_docx"],
            fallback_backend="none",
            registry=self.registry,
        )
        self.assertEqual(report["selection"]["status"], "REPAIR_REQUIRES_DEDICATED_WORKFLOW")

    def test_pdf_audit_can_use_declared_native_agent(self):
        path = self.dir / "manual.pdf"
        path.write_bytes(b"%PDF-1.7\n")
        report = preflight_document(
            path,
            intent="audit",
            declared_backends=["native_agent"],
            fallback_backend="none",
            registry=self.registry,
        )
        self.assertEqual(report["selection"]["status"], "READY")
        self.assertEqual(report["selection"]["selected_backend"], "native_agent")

    def test_pdf_repair_is_dedicated(self):
        path = self.dir / "manual.pdf"
        path.write_bytes(b"%PDF-1.7\n")
        report = preflight_document(
            path,
            intent="repair",
            declared_backends=["native_agent"],
            fallback_backend="none",
            registry=self.registry,
        )
        self.assertEqual(report["selection"]["status"], "REPAIR_REQUIRES_DEDICATED_WORKFLOW")

    def test_text_uses_builtin_text(self):
        path = self.dir / "note.txt"
        path.write_text("plain text\n", encoding="utf-8")
        report = preflight_document(path, intent="audit", fallback_backend="none", registry=self.registry)
        self.assertEqual(report["selection"]["status"], "READY")
        self.assertEqual(report["selection"]["selected_backend"], "builtin_text")

    def test_no_backend_is_explicit(self):
        path = self.dir / "manual.pdf"
        path.write_bytes(b"%PDF-1.7\n")
        capabilities = probe_capabilities([], self.registry)
        for name in ["pypdf", "markitdown", "docling", "tika", "native_agent"]:
            capabilities["backends"][name]["available"] = False
            capabilities["backends"][name]["source"] = "UNAVAILABLE"
        probe = {
            "format_version": "1.0",
            "path": str(path),
            "file_size": path.stat().st_size,
            "declared_format": "pdf",
            "detected_format": "pdf",
            "effective_format": "pdf",
            "task_context_format": "pdf",
            "family": "pdf",
            "confidence": "HIGH",
            "status": "MATCH",
            "container": None,
            "macro_enabled": False,
            "risk_flags": ["READ_ONLY_DEFAULT"],
            "evidence": ["synthetic"],
        }
        selection = select_backend(probe, capabilities, "audit", self.registry)
        self.assertEqual(selection["status"], "NO_BACKEND")

    def test_task_context_mapping_is_supported(self):
        supported = set(__import__("json").loads((ROOT / "schemas/task_context.schema.json").read_text())["properties"]["format"]["enum"])
        for fmt, spec in self.registry["formats"].items():
            self.assertIn(spec["task_context_format"], supported, fmt)

    def test_new_structured_format_routes_format_policy(self):
        context = {
            "format_version": "1.0",
            "mode": "AUDIT",
            "format": "odt",
            "signals": {
                "has_project_glossary": False,
                "aligned_bilingual_units": False,
                "structured_output": False,
                "needs_external_evidence": False,
                "external_research_requested": False,
                "public_research_permitted": False,
                "approved_resource_resolves_scope": False,
                "repair_requested": False,
                "repair_authorized": False
            },
            "risk_tags": []
        }
        plan = build_plan(
            context,
            config=load_router_config(),
            check_package_paths=False,
        )
        self.assertIn(
            "references/06_FILE_STRUCTURE_AND_FORMAT_POLICY.md",
            plan["load_now"],
        )


if __name__ == "__main__":
    unittest.main()

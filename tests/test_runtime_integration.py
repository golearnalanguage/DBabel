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

from prepare_runtime import prepare_runtime, validate_runtime_plan
from route_resources import build_plan, load_router_config


class RuntimeIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def make_docx(self, name="manual.docx", macro=False):
        path = self.dir / name
        with zipfile.ZipFile(str(path), "w", compression=zipfile.ZIP_STORED) as zf:
            zf.writestr(
                "[Content_Types].xml",
                "<Types>{}</Types>".format("macroEnabled" if macro else ""),
            )
            zf.writestr("word/document.xml", "<w:document/>")
            if macro:
                zf.writestr("word/vbaProject.bin", b"synthetic")
        return path

    def test_inline_lookup_does_not_load_file_runtime_policy(self):
        plan = prepare_runtime(mode="LOOKUP")
        self.assertEqual(plan["runtime"]["status"], "READY_FOR_TASK")
        self.assertIsNone(plan["preflight"])
        self.assertEqual(plan["task_context"]["input_kind"], "inline_text")
        self.assertIn(
            "references/03_TERMINOLOGY_CLASSIFICATION.md",
            plan["resource_plan"]["load_now"],
        )
        self.assertNotIn(
            "references/17_RUNTIME_PREFLIGHT_AND_INGEST_VALIDATION.md",
            plan["resource_plan"]["load_now"],
        )

    def test_file_runtime_routes_preflight_and_format_policy(self):
        plan = prepare_runtime(
            mode="AUDIT",
            file_path=self.make_docx(),
            declared_backends=["native_agent"],
            fallback_backend="none",
        )
        self.assertEqual(plan["runtime"]["status"], "READY_FOR_INGEST")
        self.assertEqual(plan["task_context"]["format"], "docx")
        self.assertEqual(plan["task_context"]["preflight_status"], "READY")
        self.assertIn(
            "references/17_RUNTIME_PREFLIGHT_AND_INGEST_VALIDATION.md",
            plan["resource_plan"]["load_now"],
        )
        self.assertIn(
            "references/06_FILE_STRUCTURE_AND_FORMAT_POLICY.md",
            plan["resource_plan"]["load_now"],
        )

    def test_content_extension_conflict_blocks_runtime(self):
        plan = prepare_runtime(
            mode="AUDIT",
            file_path=self.make_docx("manual.pdf"),
            declared_backends=["native_agent"],
            fallback_backend="none",
        )
        self.assertEqual(plan["runtime"]["status"], "BLOCKED")
        self.assertEqual(plan["task_context"]["format"], "unknown")
        self.assertEqual(
            plan["task_context"]["preflight_status"],
            "BLOCKED_FORMAT_CONFLICT",
        )
        self.assertIn(
            "references/17_RUNTIME_PREFLIGHT_AND_INGEST_VALIDATION.md",
            plan["resource_plan"]["load_now"],
        )
        self.assertNotIn(
            "references/06_FILE_STRUCTURE_AND_FORMAT_POLICY.md",
            plan["resource_plan"]["load_now"],
        )

    def test_bilingual_file_routes_only_relevant_accuracy_resources(self):
        plan = prepare_runtime(
            mode="BILINGUAL_REVIEW",
            file_path=self.make_docx(),
            declared_backends=["native_agent"],
            fallback_backend="none",
            has_project_glossary=True,
            aligned_bilingual_units=True,
            risk_tags=["execution_scope"],
        )
        load = plan["resource_plan"]["load_now"]
        self.assertIn("references/07_TRANSLATION_AND_MT_POLICY.md", load)
        self.assertIn("references/14_PROJECT_TERMINOLOGY_RESOLUTION.md", load)
        self.assertIn("references/15_DETERMINISTIC_BILINGUAL_QA.md", load)
        self.assertIn("references/17_RUNTIME_PREFLIGHT_AND_INGEST_VALIDATION.md", load)
        self.assertEqual(plan["resource_plan"]["example_sections"], ["A2"])
        self.assertNotIn("references/13_SEARCH_AND_RETRIEVAL_STRATEGY.md", load)

    def test_bilingual_without_alignment_does_not_route_deterministic_qa(self):
        plan = prepare_runtime(
            mode="BILINGUAL_REVIEW",
            file_path=self.make_docx(),
            declared_backends=["native_agent"],
            fallback_backend="none",
            aligned_bilingual_units=False,
        )
        self.assertNotIn(
            "references/15_DETERMINISTIC_BILINGUAL_QA.md",
            plan["resource_plan"]["load_now"],
        )

    def test_repair_mode_implies_repair_requested(self):
        plan = prepare_runtime(
            mode="REPAIR",
            inline_format="txt",
        )
        self.assertTrue(plan["task_context"]["signals"]["repair_requested"])
        self.assertFalse(plan["task_context"]["signals"]["repair_authorized"])

    def test_repair_authorized_implies_requested(self):
        plan = prepare_runtime(
            mode="AUDIT",
            repair_authorized=True,
        )
        self.assertTrue(plan["task_context"]["signals"]["repair_requested"])
        self.assertTrue(plan["task_context"]["signals"]["repair_authorized"])
        self.assertIn(
            "references/08_QA_AND_RELEASE_GATES.md",
            plan["resource_plan"]["load_now"],
        )

    def test_runtime_plan_schema_is_valid(self):
        plan = prepare_runtime(mode="LOOKUP")
        self.assertEqual(validate_runtime_plan(plan), [])

    def test_file_context_requires_preflight_status(self):
        context = {
            "format_version": "1.0",
            "mode": "AUDIT",
            "format": "docx",
            "input_kind": "file",
            "signals": {
                "has_project_glossary": False,
                "aligned_bilingual_units": False,
                "structured_output": False,
                "needs_external_evidence": False,
                "external_research_requested": False,
                "public_research_permitted": False,
                "approved_resource_resolves_scope": False,
                "repair_requested": False,
                "repair_authorized": False,
            },
            "risk_tags": [],
        }
        with self.assertRaises(ValueError):
            build_plan(context, config=load_router_config(), check_package_paths=False)


    def test_workflow_declares_closed_runtime_loop(self):
        import yaml
        workflow = yaml.safe_load(
            (ROOT / "config/workflow.yaml").read_text(encoding="utf-8")
        )
        states = workflow["states"]
        for required in (
            "TASK_CONTEXT",
            "FORMAT_PROBE",
            "CAPABILITY_PROBE",
            "RESOURCE_ROUTING",
            "INGEST",
            "INGEST_VALIDATION",
            "DETERMINISTIC_QA",
            "ROUND_TRIP_QA",
        ):
            self.assertIn(required, states)
        self.assertFalse(workflow["rules"]["full_reference_sweep_allowed"])
        self.assertFalse(workflow["rules"]["file_extension_is_format_proof"])
        self.assertFalse(workflow["rules"]["preflight_ready_is_ingest_success"])
        self.assertFalse(workflow["rules"]["deterministic_qa_authorizes_repair"])

    def test_kernel_is_progressive_not_full_sweep(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Do not perform a precautionary full-reference sweep", skill)
        self.assertIn("load only", skill.lower())
        self.assertIn("scripts/prepare_runtime.py", skill)


if __name__ == "__main__":
    unittest.main()

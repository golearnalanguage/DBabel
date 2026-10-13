"""Declared applicability must reach planning and models without extra metadata."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from runtime.memory_scope import known_context
from runtime.orchestrator import OrchestrationError, RuntimeOrchestrator
from runtime.semantic_adjudication import build_request as semantic_request, SemanticLimits
from runtime.translation import build_generation_request, TranslationLimits
from tests.test_runtime_resume import InterruptingProvider
from prepare_runtime import prepare_runtime, validate_runtime_plan
from review_chat import chat_request

ROOT = Path(__file__).resolve().parents[1]


class ContextSyncTests(unittest.TestCase):
    def setUp(self):
        self.storage = tempfile.TemporaryDirectory()
        self.root = Path(self.storage.name)
        (self.root / "rejections.json").write_text("[]", encoding="utf-8")
        self.environment = patch.dict(os.environ, {
            "DBABEL_TRANSLATION_MEMORY": str(self.root / "memory.sqlite3"),
            "DBABEL_GENERAL_TERMS_SETTINGS": str(self.root / "settings.json"),
            "DBABEL_REJECTION_MEMORY": str(self.root / "rejections.json"),
        })
        self.environment.start()
        self.source = self.root / "source.txt"
        self.source.write_text("配置主库\n检查主库\n启动主库\n", encoding="utf-8")
        self.config = self.root / "provider.json"
        self.config.write_text(json.dumps({
            "provider": "openai-compatible", "base_url": "https://example.com/v1",
            "api_key_env": "DBABEL_TEST_KEY", "model": "fake-model",
        }), encoding="utf-8")
        self.workspace = self.root / "runs"
        self.orchestrator = RuntimeOrchestrator(workspace_root=self.workspace)

    def tearDown(self):
        self.environment.stop()
        self.storage.cleanup()

    def context(self):
        return {"project_id": " manual-project ", "vendor": " Example ",
                "product": " Database A ", "version": " 4.2 ", "domain": " HA ",
                "private_note": "DO_NOT_SEND", "approval": True, "unknown": {"secret": "DO_NOT_SEND"}}

    def run_pipeline(self, provider, context=None, resume_run=None):
        return self.orchestrator.run_translation_to_review(
            source=self.source, source_language="zh-CN", target_language="en",
            provider_config_path=self.config, default_text_role="PROSE", provider=provider,
            context=context, resume_run=resume_run,
            translation_limits=TranslationLimits(max_units_per_batch=1),
            semantic_limits=SemanticLimits(max_units_per_batch=1))

    def test_whitelist_omits_empty_fields_and_local_document_identity_for_models(self):
        context = {"project_id": "document:" + "a" * 64, "product": "Database A",
                   "version": None, "vendor": "  ", "text_role": "PROSE", "private_note": "DO_NOT_SEND"}
        local = known_context(context)
        self.assertEqual(local, {"project_id": context["project_id"], "product": "Database A", "text_role": "PROSE"})
        selected = {"id": "U1", "source": "配置主库", "suggested_target": "Configure the primary database.",
                    "context": context, "scope_key": "LOCAL_HASH_DO_NOT_SEND"}
        expected = {"product": "Database A", "text_role": "PROSE"}
        for request in (build_generation_request([selected], "zh-CN", "en"),
                        semantic_request([selected], {}, "zh-CN", "en")):
            payload = json.loads(request.user)
            self.assertEqual(payload["units"][0]["context"], expected)
            self.assertNotIn(context["project_id"], request.user)
            self.assertNotIn("DO_NOT_SEND", request.user)
            self.assertNotIn("LOCAL_HASH", request.user)
        with self.assertRaisesRegex(ValueError, "must be text"):
            known_context({"product": {"name": "Database A"}})

    def test_payload_preserves_explicit_project_and_known_context(self):
        context = self.context()
        context["text_role"] = "PROSE"
        selected = {"id": "U1", "source": "配置主库", "suggested_target": "Configure the primary database.",
                    "context": context}
        expected = known_context(context)
        for request in (build_generation_request([selected], "zh-CN", "en"),
                        semantic_request([selected], {}, "zh-CN", "en")):
            self.assertEqual(json.loads(request.user)["units"][0]["context"], expected)
            self.assertNotIn("DO_NOT_SEND", request.user)
        # Older artifacts with only the required role remain valid inputs.
        selected["context"] = {"text_role": "PROSE"}
        self.assertEqual(json.loads(build_generation_request([selected], "zh-CN", "en").user)
                         ["units"][0]["context"], {"text_role": "PROSE"})

    def test_prepare_runtime_accepts_project_scope_and_cli_from_another_directory(self):
        context = self.context()
        context["text_role"] = "PROSE"
        context["domain"] = " "
        plan = prepare_runtime(mode="LOOKUP", scope=context)
        self.assertEqual(plan["task_context"]["scope"], known_context(context))
        self.assertEqual(validate_runtime_plan(plan), [])
        self.assertNotIn("DO_NOT_SEND", json.dumps(plan))
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "prepare_runtime.py"),
                                 "--mode", "LOOKUP", "--project-id", "manual-project", "--product", "Database A"],
                                cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["task_context"]["scope"],
                         {"project_id": "manual-project", "product": "Database A"})

    def test_review_chat_keeps_selected_language_and_declared_scope(self):
        context = self.context()
        selected = {"id": "U1", "source": "配置主库", "source_language": "zh-CN",
                    "target_language": "en", "text_role": "PROSE", "context": context}
        data = {"session": {"source_language": "zh-CN", "target_languages": ["en", "ja"]},
                "units_by_id": {"U1": selected}, "issues": [], "evidence": []}
        request = chat_request(data, [], "U1", "Explain the wording.")
        unit = json.loads(request.user)["selected_unit"]
        self.assertEqual(unit["context"], known_context(context))
        self.assertEqual(unit["target_language"], "en")
        self.assertEqual(unit["text_role"], "PROSE")
        self.assertNotIn("DO_NOT_SEND", request.user)
        selected["context"] = {"project_id": "document:" + "a" * 64}
        unit = json.loads(chat_request(data, [], "U1", "Explain.").user)["selected_unit"]
        self.assertNotIn("context", unit)

    def test_pipeline_shares_context_between_plan_ingest_models_and_review(self):
        class CapturingProvider(InterruptingProvider):
            def __init__(self):
                super().__init__()
                self.requests = []
            def generate(self, request):
                self.requests.append(request)
                return super().generate(request)
        provider = CapturingProvider()
        result = self.run_pipeline(provider, context=self.context())
        self.assertEqual(result["status"], "READY_FOR_HUMAN_REVIEW")
        expected = dict(known_context(self.context()), text_role="PROSE")
        self.assertEqual(result["memory_context"], expected)
        plan = json.loads(Path(result["artifacts"]["runtime_plan"]["path"]).read_text())
        self.assertEqual(plan["task_context"]["scope"], expected)
        ingest = json.loads(Path(result["artifacts"]["ingest"]["path"]).read_text())
        self.assertTrue(all(unit["context"] == expected for unit in ingest["units"]))
        self.assertEqual(len(provider.requests), 6)
        for request in provider.requests:
            self.assertTrue(all(unit["context"] == expected for unit in json.loads(request.user)["units"]))
            self.assertNotIn("DO_NOT_SEND", request.user)
        bundle = Path(result["artifacts"]["review_bundle"]["path"])
        review_units = [json.loads(line) for line in (bundle / "units.jsonl").read_text().splitlines()]
        self.assertTrue(all(unit["context"] == expected for unit in review_units))

    def test_resume_accepts_explicit_scope_saved_by_older_runs(self):
        with self.assertRaisesRegex(OrchestrationError, "402"):
            self.run_pipeline(InterruptingProvider(fail_stage="ADJUDICATION"), context=self.context())
        manifest_path = next(self.workspace.glob("RUN_*/run.json"))
        saved = json.loads(manifest_path.read_text())
        saved["memory_context"].pop("text_role")
        manifest_path.write_text(json.dumps(saved), encoding="utf-8")
        provider = InterruptingProvider()
        result = self.run_pipeline(provider, context=self.context(), resume_run=manifest_path.parent)
        self.assertEqual(result["status"], "READY_FOR_HUMAN_REVIEW")
        self.assertEqual(provider.calls["TRANSLATION"], [])
        self.assertEqual(len(provider.calls["ADJUDICATION"]), 2)

    def test_conflicting_role_fails_before_creating_a_run(self):
        provider = InterruptingProvider()
        with self.assertRaisesRegex(OrchestrationError, "text role"):
            self.run_pipeline(provider, context={"text_role": "UI_LABEL"})
        self.assertFalse(self.workspace.exists())
        self.assertEqual(provider.calls, {"TRANSLATION": [], "ADJUDICATION": []})

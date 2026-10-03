"""A failed provider batch must not charge again for saved successful batches."""
import json
import tempfile
import unittest
from pathlib import Path

from providers.base import ProviderError
from runtime.models import GenerationResponse
from runtime.orchestrator import OrchestrationError, RuntimeOrchestrator
from runtime.semantic_adjudication import SemanticLimits
from runtime.translation import TranslationLimits


class InterruptingProvider:
    def __init__(self, fail_stage=None, fail_call=2):
        self.fail_stage = fail_stage
        self.fail_call = fail_call
        self.calls = {"TRANSLATION": [], "ADJUDICATION": []}

    def generate(self, request):
        payload = json.loads(request.user)
        stage = ("ADJUDICATION" if payload.get("task") == "DBabel semantic risk adjudication"
                 else "TRANSLATION")
        ids = [unit["id"] for unit in payload["units"]]
        self.calls[stage].append(ids)
        if stage == self.fail_stage and len(self.calls[stage]) == self.fail_call:
            raise ProviderError("HTTP 402: balance exhausted")
        rows = []
        for unit in payload["units"]:
            if stage == "ADJUDICATION":
                rows.append({"id": unit["id"], "outcome": "NO_FINDING",
                             "classification": None, "reason": "No concern in context.",
                             "next_action": ""})
            else:
                rows.append({"id": unit["id"],
                             "suggested_target": "Configure the primary database.",
                             "proposal_decision": "REPLACE", "reason": "Instruction translated."})
        return GenerationResponse(text=json.dumps({"units": rows}), model="fake-model",
                                  provider="fake-provider", response_id="fake-response",
                                  usage={"total_tokens": 1})


class RuntimeResumeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source.txt"
        self.source.write_text("配置主库\n检查主库\n启动主库\n", encoding="utf-8")
        self.config = self.root / "provider.json"
        self.config.write_text(json.dumps({
            "provider": "openai-compatible", "base_url": "https://example.com/v1",
            "api_key_env": "DBABEL_TEST_KEY", "model": "fake-model",
            "timeout_seconds": 120, "max_response_bytes": 2000000,
        }))
        self.workspace = self.root / "runs"
        self.orchestrator = RuntimeOrchestrator(workspace_root=self.workspace)

    def tearDown(self):
        self.temp.cleanup()

    def run_pipeline(self, provider, resume_run=None):
        return self.orchestrator.run_translation_to_review(
            source=self.source, source_language="zh-CN", target_language="en",
            provider_config_path=self.config, default_text_role="PROSE",
            provider=provider, resume_run=resume_run,
            translation_limits=TranslationLimits(max_units_per_batch=1),
            semantic_limits=SemanticLimits(max_units_per_batch=1),
        )

    def failed_run(self, stage):
        with self.assertRaisesRegex(OrchestrationError, "402"):
            self.run_pipeline(InterruptingProvider(fail_stage=stage))
        runs = list(self.workspace.glob("RUN_*/run.json"))
        self.assertEqual(len(runs), 1)
        manifest = json.loads(runs[0].read_text())
        self.assertEqual(manifest["status"], "FAILED")
        self.assertEqual(manifest["current_stage"], stage)
        return runs[0].parent, manifest

    def test_semantic_resume_skips_saved_batches_and_translation(self):
        root, failed = self.failed_run("ADJUDICATION")
        self.assertEqual(len(json.loads((root / "semantic-checkpoint.json").read_text())["items"]), 1)
        provider = InterruptingProvider()
        result = self.run_pipeline(provider, resume_run=root)
        self.assertEqual(result["status"], "READY_FOR_HUMAN_REVIEW")
        self.assertEqual(result["run_id"], failed["run_id"])
        self.assertEqual(provider.calls["TRANSLATION"], [])
        self.assertEqual(len(provider.calls["ADJUDICATION"]), 2)
        self.assertEqual(self.source.read_text(), "配置主库\n检查主库\n启动主库\n")

    def test_translation_resume_skips_saved_batch(self):
        root, failed = self.failed_run("TRANSLATION")
        self.assertEqual(len(json.loads((root / "translation-checkpoint.json").read_text())["items"]), 1)
        provider = InterruptingProvider()
        result = self.run_pipeline(provider, resume_run=root / "run.json")
        self.assertEqual(result["status"], "READY_FOR_HUMAN_REVIEW")
        self.assertEqual(result["run_id"], failed["run_id"])
        self.assertEqual(len(provider.calls["TRANSLATION"]), 2)

    def test_transport_changes_resume_successful_batches(self):
        root, _ = self.failed_run("ADJUDICATION")
        config = json.loads(self.config.read_text())
        config.update(timeout_seconds=300, stream=True, proxy_mode="none", temperature_mode="omit",
                      extra_body={"thinking": {"type": "disabled"}})
        self.config.write_text(json.dumps(config))
        provider = InterruptingProvider()
        result = self.run_pipeline(provider, resume_run=root)
        self.assertEqual(result["status"], "READY_FOR_HUMAN_REVIEW")
        self.assertEqual(provider.calls["TRANSLATION"], [])
        self.assertEqual(len(provider.calls["ADJUDICATION"]), 2)

    def test_changed_provider_identity_refuses_resume(self):
        root, _ = self.failed_run("ADJUDICATION")
        config = json.loads(self.config.read_text())
        config["model"] = "different-model"
        self.config.write_text(json.dumps(config))
        provider = InterruptingProvider()
        with self.assertRaisesRegex(OrchestrationError, "API service"):
            self.run_pipeline(provider, resume_run=root)
        self.assertEqual(provider.calls["ADJUDICATION"], [])

    def test_changed_source_refuses_resume_before_provider_call(self):
        root, _ = self.failed_run("ADJUDICATION")
        self.source.write_text("changed\n", encoding="utf-8")
        provider = InterruptingProvider()
        with self.assertRaisesRegex(ValueError, "source file changed"):
            self.run_pipeline(provider, resume_run=root)
        self.assertEqual(provider.calls["TRANSLATION"], [])
        self.assertEqual(provider.calls["ADJUDICATION"], [])

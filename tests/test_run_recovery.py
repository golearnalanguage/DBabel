"""Real process death and run ownership must preserve completed batches."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from runtime.orchestrator import RuntimeOrchestrator, OrchestrationError
from runtime.run_lease import RunLease, RunBusyError, probe_run_liveness, resumable_runs
from runtime.translation import TranslationLimits
from tests.test_runtime_resume import InterruptingProvider

ROOT = Path(__file__).resolve().parents[1]


class RunRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.storage = tempfile.TemporaryDirectory()
        base = Path(self.storage.name)
        (base / 'rejections.json').write_text('[]')
        self.environment = patch.dict(os.environ, {
            'DBABEL_TRANSLATION_MEMORY': str(base / 'memory.sqlite3'),
            'DBABEL_GENERAL_TERMS_SETTINGS': str(base / 'settings.json'),
            'DBABEL_REJECTION_MEMORY': str(base / 'rejections.json')})
        self.environment.start()
    def tearDown(self):
        self.environment.stop()
        self.storage.cleanup()
    def test_lock_is_exclusive_and_released(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(probe_run_liveness(root), "UNKNOWN")
            with RunLease(root):
                self.assertIn(probe_run_liveness(root), {"ACTIVE", "UNKNOWN"})
                with self.assertRaises(RunBusyError):
                    with RunLease(root):
                        self.fail("second owner acquired the lock")
            self.assertEqual(probe_run_liveness(root), "INACTIVE")

    def test_killed_owner_recovers_without_repeating_saved_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.txt"
            source.write_text("配置主库\n检查主库\n启动主库\n", encoding="utf-8")
            config = root / "provider.json"
            config.write_text(json.dumps({"provider": "openai-compatible", "base_url": "https://example.com/v1",
                "api_key_env": "DBABEL_TEST_KEY", "model": "fake-model"}))
            (root / "rejections.json").write_text('[]')
            script = root / "child.py"
            script.write_text('''import json,sys,time
from pathlib import Path
from runtime.orchestrator import RuntimeOrchestrator
from runtime.translation import TranslationLimits
from tests.test_runtime_resume import InterruptingProvider
root=Path(sys.argv[1])
class Blocking(InterruptingProvider):
 def generate(self,request):
  payload=json.loads(request.user)
  if payload['units'][0]['id'].startswith('U00002'):
   (root/'waiting').write_text('ready')
   time.sleep(120)
  return super().generate(request)
RuntimeOrchestrator(workspace_root=root/'runs').run_translation_to_review(
 source=root/'source.txt',source_language='zh-CN',target_language='en',
 provider_config_path=root/'provider.json',default_text_role='PROSE',
 provider=Blocking(),translation_limits=TranslationLimits(max_units_per_batch=1))
''')
            env = dict(os.environ, PYTHONPATH=str(ROOT), DBABEL_TRANSLATION_MEMORY=str(root / "memory.sqlite3"),
                       DBABEL_GENERAL_TERMS_SETTINGS=str(root / "general.json"), DBABEL_REJECTION_MEMORY=str(root / "rejections.json"))
            child = subprocess.Popen([sys.executable, str(script), str(root)], env=env,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 20
                while not (root / "waiting").exists() and child.poll() is None and time.monotonic() < deadline:
                    time.sleep(.05)
                if not (root / "waiting").exists() and child.poll() is not None:
                    stdout, stderr = child.communicate()
                    self.fail("child failed before the second batch: " + stderr.decode(errors='replace'))
                self.assertTrue((root / "waiting").exists(), "child did not reach the second provider batch")
                run = next((root / "runs").glob("RUN_*"))
                orchestrator = RuntimeOrchestrator(workspace_root=root / "runs")
                kwargs = dict(source=source, source_language="zh-CN", target_language="en",
                    provider_config_path=config, default_text_role="PROSE", resume_run=run,
                    translation_limits=TranslationLimits(max_units_per_batch=1))
                with self.assertRaisesRegex(OrchestrationError, "active|unknown"):
                    orchestrator.run_translation_to_review(provider=InterruptingProvider(), **kwargs)
                child.kill()
                child.communicate(timeout=5)
                self.assertEqual(len(resumable_runs(root / "runs")), 1)
                provider = InterruptingProvider()
                result = orchestrator.run_translation_to_review(provider=provider, **kwargs)
                self.assertEqual(result["status"], "READY_FOR_HUMAN_REVIEW")
                self.assertEqual(len(provider.calls["TRANSLATION"]), 2)
                self.assertEqual(probe_run_liveness(run), "INACTIVE")
            finally:
                if child.poll() is None:
                    child.kill()
                child.communicate(timeout=5)

    def test_killed_owner_after_semantic_save_reuses_all_provider_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.txt"
            source.write_text("配置主库\n", encoding="utf-8")
            config = root / "provider.json"
            config.write_text(json.dumps({"provider": "openai-compatible", "base_url": "https://example.com/v1",
                "api_key_env": "DBABEL_TEST_KEY", "model": "fake-model"}))
            script = root / "child.py"
            script.write_text('''import sys,time
from pathlib import Path
import runtime.orchestrator as orchestration
from tests.test_runtime_resume import InterruptingProvider
root=Path(sys.argv[1])
def block_review_binding(**kwargs):
 (root/'waiting').write_text('ready')
 time.sleep(120)
 raise AssertionError('parent should kill the owner before this point')
orchestration.bind_review_session=block_review_binding
orchestration.RuntimeOrchestrator(workspace_root=root/'runs').run_translation_to_review(
 source=root/'source.txt',source_language='zh-CN',target_language='en',
 provider_config_path=root/'provider.json',default_text_role='PROSE',
 provider=InterruptingProvider())
''')
            env = dict(os.environ, PYTHONPATH=str(ROOT))
            child = subprocess.Popen([sys.executable, str(script), str(root)], env=env,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 20
                while not (root / "waiting").exists() and child.poll() is None and time.monotonic() < deadline:
                    time.sleep(.05)
                if not (root / "waiting").exists() and child.poll() is not None:
                    stdout, stderr = child.communicate()
                    self.fail("child failed before review binding: " + stderr.decode(errors='replace'))
                self.assertTrue((root / "waiting").exists(), "child did not reach review binding")
                run = next((root / "runs").glob("RUN_*"))
                saved = json.loads((run / "run.json").read_text())
                self.assertEqual(saved["status"], "SEMANTIC_ADJUDICATION_READY")
                self.assertIn("semantic_adjudication", saved["artifacts"])
                self.assertEqual(resumable_runs(root / "runs"), [])
                child.kill()
                child.communicate(timeout=5)
                candidates = resumable_runs(root / "runs")
                self.assertEqual(len(candidates), 1)
                self.assertEqual(candidates[0]["status"], "SEMANTIC_ADJUDICATION_READY")
                provider = InterruptingProvider()
                result = RuntimeOrchestrator(workspace_root=root / "runs").run_translation_to_review(
                    source=source, source_language="zh-CN", target_language="en",
                    provider_config_path=config, default_text_role="PROSE", resume_run=run,
                    provider=provider)
                self.assertEqual(result["status"], "READY_FOR_HUMAN_REVIEW")
                self.assertEqual(provider.calls, {"TRANSLATION": [], "ADJUDICATION": []})
                self.assertEqual(probe_run_liveness(run), "INACTIVE")
            finally:
                if child.poll() is None:
                    child.kill()
                child.communicate(timeout=5)

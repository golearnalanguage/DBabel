"""A reachable gateway must also satisfy the small translation contract."""
import json
import unittest
from runtime.models import GenerationResponse
from providers.preflight import task_preflight


class TaskPreflightTests(unittest.TestCase):
    def provider(self, text):
        class Provider:
            def generate(self, request):
                return GenerationResponse(text, "test", "fake", None, {})
        return Provider()

    def test_valid_translation_contract(self):
        text = json.dumps({"units": [{"id": "PROBE_1", "suggested_target":
            "Check /data/db/dm.ini and confirm that ${DB_HOME} and --exec_mode remain unchanged."}]})
        self.assertTrue(task_preflight(self.provider(text))["contract_verified"])

    def test_connection_only_text_or_changed_path_fails(self):
        for text in ["OK", json.dumps({"units": [{"id": "PROBE_1", "suggested_target": "Check /data/wrong.ini."}]}),
                     json.dumps({"units": [{"id": "wrong", "suggested_target": "English."}]})]:
            report = task_preflight(self.provider(text))
            self.assertTrue(report["connected"])
            self.assertFalse(report["contract_verified"])

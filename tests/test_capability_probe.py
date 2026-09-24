import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from format_registry import FormatRegistryError, load_registry, validate_registry
from probe_capabilities import CapabilityError, probe_capabilities


class CapabilityProbeTests(unittest.TestCase):
    def test_registry_valid(self):
        registry = load_registry()
        self.assertEqual(validate_registry(registry), [])

    def test_builtins_available(self):
        report = probe_capabilities()
        self.assertTrue(report["backends"]["builtin_probe"]["available"])
        self.assertEqual(report["backends"]["builtin_probe"]["source"], "BUILTIN")
        self.assertTrue(report["backends"]["builtin_text"]["available"])

    def test_native_agent_requires_declaration(self):
        report = probe_capabilities()
        self.assertFalse(report["backends"]["native_agent"]["available"])
        declared = probe_capabilities(["native_agent"])
        self.assertTrue(declared["backends"]["native_agent"]["available"])
        self.assertEqual(declared["backends"]["native_agent"]["source"], "DECLARED")

    def test_unknown_declaration_rejected(self):
        with self.assertRaises(CapabilityError):
            probe_capabilities(["not_a_backend"])

    def test_every_registry_backend_reported(self):
        registry = load_registry()
        report = probe_capabilities()
        self.assertEqual(set(registry["backends"]), set(report["backends"]))

    def test_report_schema(self):
        report = probe_capabilities()
        schema = json.loads((ROOT / "schemas/capability_report.schema.json").read_text())
        from jsonschema import Draft202012Validator
        self.assertEqual(list(Draft202012Validator(schema).iter_errors(report)), [])


if __name__ == "__main__":
    unittest.main()

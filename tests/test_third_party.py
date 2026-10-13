"""Dependency declarations match pins; actual license bytes survive inventory."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_third_party import check, export_installed


class ThirdPartyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repo"
        self.root.mkdir()
        for relative in ("config/third_party_components.json", "requirements-integration.txt", "requirements-property.txt",
                         "package.json", "package-lock.json"):
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)

    def test_static_pins_are_consistent_and_reference_is_not_installed(self):
        self.assertEqual(check(self.root), [])
        path = self.root / "config/third_party_components.json"
        declaration = json.loads(path.read_text())
        declaration["components"][0]["version"] = "9.9.9"
        path.write_text(json.dumps(declaration))
        self.assertTrue(any("runtime integration pin" in error for error in check(self.root)))
        declaration["components"][0]["version"] = "3.29.0"
        next(c for c in declaration["components"] if c["kind"] == "reference")["version"] = "1.0.0"
        path.write_text(json.dumps(declaration))
        self.assertTrue(any("reference must not claim" in error for error in check(self.root)))

    def test_installed_license_and_native_notice_are_retained_verbatim(self):
        site = Path(self.temporary.name) / "site"
        info = site / "lxml-6.1.3.dist-info"
        (info / "licenses").mkdir(parents=True)
        (info / "METADATA").write_text("Metadata-Version: 2.4\nName: lxml\nVersion: 6.1.3\nLicense-Expression: BSD-3-Clause\n")
        source = b"Native library notices: iconv LGPL-2.1; libxml2 MIT\n"
        (info / "licenses/LICENSES.txt").write_bytes(source)
        (info / "RECORD").write_text("lxml-6.1.3.dist-info/METADATA,,\nlxml-6.1.3.dist-info/licenses/LICENSES.txt,,\n")
        output = Path(self.temporary.name) / "inventory"
        report = export_installed(output, self.root, [site])
        self.assertEqual(report["issues"], [])
        material = report["installed"][0]["materials"][0]
        self.assertEqual((output / material["path"]).read_bytes(), source)
        self.assertIn("anthropic", report["not_installed"])
        self.assertFalse(any(c["name"] == "REA" for c in report["installed"]))
        self.assertTrue((output / "inventory.json").is_file())
        with self.assertRaises(FileExistsError):
            export_installed(output, self.root, [site])

    def test_unknown_license_and_absent_notice_are_reported(self):
        site = Path(self.temporary.name) / "unknown"
        info = site / "example-1.0.dist-info"
        info.mkdir(parents=True)
        (info / "METADATA").write_text("Metadata-Version: 2.4\nName: example\nVersion: 1.0\n")
        report = export_installed(Path(self.temporary.name) / "missing", self.root, [site])
        self.assertEqual({i["reason"] for i in report["issues"]},
                         {"NO_LICENSE_OR_NOTICE_MATERIAL", "LICENSE_METADATA_UNKNOWN"})
        self.assertIsNone(report["installed"][0]["declared_license"])

    def test_node_dependency_third_party_notices_are_retained(self):
        package = self.root / "node_modules/axe-core"
        package.mkdir(parents=True)
        (package / "package.json").write_text(json.dumps({"name": "axe-core", "version": "4.11.0", "license": "MPL-2.0"}))
        (package / "LICENSE").write_text("MPL license material")
        original = b"Preserve nested upstream copyrights\n"
        (package / "ThirdPartyNotices.txt").write_bytes(original)
        empty_site = Path(self.temporary.name) / "empty"
        empty_site.mkdir()
        output = Path(self.temporary.name) / "node-inventory"
        report = export_installed(output, self.root, [empty_site])
        self.assertEqual(report["issues"], [])
        row = report["installed"][0]
        self.assertEqual(len(row["materials"]), 2)
        receipt = next(m for m in row["materials"] if m["path"].endswith("ThirdPartyNotices.txt"))
        self.assertEqual((output / receipt["path"]).read_bytes(), original)


if __name__ == "__main__":
    unittest.main()

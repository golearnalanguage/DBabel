"""TMX exchange preserves scope/inline XML and never grants local approval."""
import json
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from tmx_exchange import export_tmx, import_tmx


@unittest.skipUnless(importlib.util.find_spec("lxml"), "Optional lxml integration dependency is unavailable")
class TmxExchangeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def source(self, xml):
        path = self.root / "input.tmx"
        path.write_text(xml, encoding="utf-8")
        return path

    def test_unicode_whitespace_scope_and_rejection_round_trip_as_unapproved(self):
        entry = {"source_language": "zh-CN", "target_language": "en-US", "source": " 日志 <归档> ",
                 "target": " log <archive> ", "text_role": "UI_LABEL", "kind": "REJECTED",
                 "decision": "BLOCKED", "scope": {"kind": "SCOPED", "context": {"product": "A", "version": "2"}},
                 "provenance": {"session_id": "owned-session"}}
        path = self.root / "roundtrip.tmx"
        path.write_bytes(export_tmx([entry]))
        result = import_tmx(path, "zh-CN", "en-US")
        candidate = result["candidates"][0]
        self.assertEqual(candidate["source"], entry["source"])
        self.assertEqual(candidate["target"], entry["target"])
        self.assertEqual(candidate["scope"], entry["scope"])
        self.assertEqual(candidate["upstream_metadata"]["kind"], "REJECTED")
        self.assertEqual(candidate["upstream_metadata"]["provenance"], entry["provenance"])
        self.assertEqual(candidate["approval"], "USER_REVIEW")
        self.assertEqual(candidate["candidate_status"], "REVIEW")
        self.assertEqual(result["memory_changes"], 0)

    def test_inline_codes_are_retained_and_not_flattened(self):
        path = self.source('<tmx version="1.4"><header/><body><tu tuid="7"><note>keep</note>'
                           '<tuv xml:lang="en"><seg>Hello <bpt i="1">&lt;b&gt;</bpt>world<ept i="1">&lt;/b&gt;</ept></seg></tuv>'
                           '<tuv xml:lang="zh"><seg>你好</seg></tuv></tu></body></tmx>')
        candidate = import_tmx(path, "en", "zh")["candidates"][0]
        self.assertIsNone(candidate["source"])
        self.assertEqual(candidate["candidate_status"], "UNSUPPORTED")
        self.assertIn('<bpt i="1">', candidate["provenance"]["unit_xml"])
        self.assertIn("keep", candidate["provenance"]["unit_xml"])

    def test_duplicate_language_and_unknown_extension_require_review(self):
        path = self.source('<tmx version="1.4"><header/><body><tu><custom>unhandled</custom>'
                           '<tuv xml:lang="en"><seg>A</seg></tuv><tuv xml:lang="en"><seg>B</seg></tuv>'
                           '<tuv xml:lang="fr"><seg>C</seg></tuv></tu></body></tmx>')
        candidate = import_tmx(path, "en", "fr")["candidates"][0]
        self.assertIsNone(candidate["source"])
        self.assertEqual(candidate["candidate_status"], "UNSUPPORTED")
        self.assertIn("unhandled", candidate["provenance"]["unit_xml"])

    def test_language_variant_does_not_fall_back_to_an_adjacent_locale(self):
        path = self.source('<tmx version="1.4"><header/><body><tu><tuv xml:lang="en-US"><seg>A</seg></tuv>'
                           '<tuv xml:lang="zh"><seg>B</seg></tuv></tu></body></tmx>')
        candidate = import_tmx(path, "en", "zh")["candidates"][0]
        self.assertIsNone(candidate["source"])
        self.assertEqual(candidate["text_role"], "UNKNOWN")
        self.assertEqual(candidate["scope"], {})

    def test_entities_are_not_read_and_unsupported_versions_are_rejected(self):
        secret = self.root / "secret.txt"
        secret.write_text("SECRET", encoding="utf-8")
        path = self.source('<!DOCTYPE tmx [<!ENTITY private SYSTEM "{}">]>'
                           '<tmx version="1.4"><header/><body><tu><tuv xml:lang="en"><seg>&private;</seg></tuv>'
                           '<tuv xml:lang="fr"><seg>B</seg></tuv></tu></body></tmx>'.format(secret.as_uri()))
        with self.assertRaisesRegex(ValueError, "entity declarations"):
            import_tmx(path, "en", "fr")
        with self.assertRaisesRegex(ValueError, "version 1.4"):
            import_tmx(self.source('<tmx version="1.3"><header/><body/></tmx>'), "en", "fr")

    def test_cli_import_creates_receipt_without_memory_file(self):
        path = self.source('<tmx version="1.4"><header/><body><tu><tuv xml:lang="en"><seg>A</seg></tuv>'
                           '<tuv xml:lang="fr"><seg>B</seg></tuv></tu></body></tmx>')
        output = self.root / "candidates.json"
        memory = self.root / "memory.sqlite3"
        env = dict(os.environ, DBABEL_TRANSLATION_MEMORY=str(memory))
        command = [sys.executable, str(ROOT / "scripts/tmx_exchange.py"), "import", str(path),
                   "--source-language", "en", "--target-language", "fr", "--output", str(output)]
        completed = subprocess.run(command, env=env, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(output.read_text())["memory_changes"], 0)
        self.assertFalse(memory.exists())
        again = subprocess.run(command, env=env, capture_output=True, text=True)
        self.assertEqual(again.returncode, 1)

    def test_cli_export_excludes_rejected_records_by_default(self):
        base = {"source_language": "en", "target_language": "fr", "source": "A", "target": "B"}
        entries = self.root / "entries.json"
        entries.write_text(json.dumps([dict(base, kind="PREFERRED"), dict(base, kind="REJECTED", target="C")]))
        output = self.root / "export.tmx"
        completed = subprocess.run([sys.executable, str(ROOT / "scripts/tmx_exchange.py"), "export", "--entries", str(entries),
                                    "--output", str(output)], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["excluded_rejected_entries"], 1)
        candidates = import_tmx(output, "en", "fr")["candidates"]
        self.assertEqual([c["target"] for c in candidates], ["B"])


if __name__ == "__main__":
    unittest.main()

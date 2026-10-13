"""Evidence source changes produce scoped review reports, preserving decisions."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from evidence_cache import check_cache, record_evidence


class EvidenceCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cache = self.root / "cache"
        self.source = self.root / "reference.txt"
        self.source.write_text("version one", encoding="utf-8")
        self.scope = {"product": "DB A", "version": "2", "text_role": "PROSE"}
        self.evidence = {"id": "E1", "source_title": "Reference", "source_type": "user_supplied_approved_resource",
                         "locator": "project://reference", "retrieved_at": "2026-10-13", "evidence_state": "CURRENT",
                         "source_opened": True, "support_note": "Supports the source subject",
                         "authority_match": "HIGH", "context_match": "HIGH", "version_match": "EXACT"}

    def record(self, **kwargs):
        return record_evidence(self.cache, self.evidence, self.source, self.scope, ["U1"], **kwargs)

    def test_idempotent_cache_and_changed_source_retain_snapshot(self):
        first = self.record()
        self.assertEqual(first, self.record())
        self.assertEqual(check_cache(self.cache, self.scope)["counts"]["CURRENT"], 1)
        self.source.write_text("version two", encoding="utf-8")
        report = check_cache(self.cache, self.scope)
        self.assertEqual(report["records"][0]["reasons"], ["SOURCE_CHANGED"])
        self.assertEqual(report["needs_review_unit_ids"], ["U1"])
        self.assertEqual((self.cache / first["source"]["snapshot"]).read_text(), "version one")

    def test_scope_missing_source_and_expiry_are_reported(self):
        self.record(expires_at="2026-10-13T01:00:00Z")
        self.source.unlink()
        report = check_cache(self.cache, {"product": "DB B"}, now=datetime(2026, 10, 14, tzinfo=timezone.utc))
        self.assertEqual(report["records"][0]["reasons"], ["SOURCE_UNAVAILABLE", "SCOPE_CHANGED", "EXPIRED"])
        self.assertEqual(report["records"][0]["evidence_state"], "STALE")

    def test_conflict_is_preserved_and_session_dependencies_are_read_only(self):
        self.evidence["evidence_state"] = "CONFLICTING"
        self.record()
        session = self.root / "test.dbreview"
        session.mkdir()
        (session / "units.jsonl").write_text(json.dumps({"id": "U2", "evidence_refs": ["E1"]}) + "\n")
        decisions = session / "decisions.json"
        decisions.write_bytes(b'{"approved":"human"}\n')
        before = decisions.read_bytes()
        report = check_cache(self.cache, session=session)
        self.assertEqual(report["records"][0]["source_evidence_state"], "CONFLICTING")
        self.assertEqual(report["needs_review_unit_ids"], ["U1", "U2"])
        self.assertEqual(report["review_decision_changes"], 0)
        self.assertEqual(decisions.read_bytes(), before)

    def test_tampered_record_and_cached_source_fail_integrity(self):
        record = self.record()
        snapshot = self.cache / record["source"]["snapshot"]
        snapshot.write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "snapshot integrity"):
            check_cache(self.cache)
        snapshot.write_text("version one", encoding="utf-8")
        path = self.cache / "records" / (record["cache_id"] + ".json")
        changed = json.loads(path.read_text())
        changed["evidence"]["support_note"] = "changed meaning"
        path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError, "record integrity"):
            check_cache(self.cache)

    def test_bad_evidence_and_naive_expiry_write_no_cache(self):
        self.evidence["id"] = "../escape"
        with self.assertRaisesRegex(ValueError, "Invalid evidence"):
            self.record()
        self.assertFalse(self.cache.exists())
        self.evidence["id"] = "E1"
        with self.assertRaisesRegex(ValueError, "timezone"):
            self.record(expires_at="2026-10-13T00:00:00")
        self.assertFalse(self.cache.exists())

    def test_cli_check_returns_two_for_stale_without_rewriting_record(self):
        record = self.record()
        path = self.cache / "records" / (record["cache_id"] + ".json")
        before = path.read_bytes()
        self.source.write_text("changed", encoding="utf-8")
        completed = subprocess.run([sys.executable, str(ROOT / "scripts/evidence_cache.py"), "check", "--cache", str(self.cache)],
                                   capture_output=True, text=True)
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["counts"]["STALE"], 1)
        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

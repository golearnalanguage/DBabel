import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_portable_review import build
from review_model import (
    default_decision,
    load_bundle,
    write_json,
    write_jsonl,
)


def make_bundle(root):
    bundle = root / "x.dbreview"
    bundle.mkdir()

    session = {
        "format_version": "1.0",
        "session_id": "RS_x",
        "created_at": "2026-01-01T00:00:00Z",
        "dbabel_version": "1.5.0-dev",
        "mode": "BILINGUAL_REVIEW",
        "title": "XSS test",
        "bundle_files": {
            "units": "units.jsonl",
            "issues": "issues.json",
            "evidence": "evidence.json",
            "decisions": "decisions.json",
            "events": "events.jsonl",
            "anchors": "anchors.json",
        },
        "original": {
            "filename": "x.docx",
            "format": "docx",
            "sha256": "0" * 64,
        },
        "counts": {
            "units": 1,
            "issues": 0,
            "evidence": 0,
        },
        "export_policy": {
            "require_all_confirmed": True,
            "block_unwaived_errors": True,
            "require_user_edit_recheck": True,
            "never_overwrite_original": True,
        },
    }

    write_json(bundle / "session.json", session)

    write_jsonl(
        bundle / "units.jsonl",
        [
            {
                "id": "U1",
                "location": "u",
                "source": "<script>alert(1)</script>",
                "current_target": "safe",
                "labels": [],
                "finding_refs": [],
                "qa_issue_refs": [],
                "evidence_refs": [],
                "requires_confirmation": True,
            }
        ],
    )

    write_json(bundle / "issues.json", [])
    write_json(bundle / "evidence.json", [])
    write_json(
        bundle / "decisions.json",
        [default_decision("U1")],
    )
    write_json(bundle / "anchors.json", {})
    (bundle / "events.jsonl").write_text("", encoding="utf-8")

    return bundle


class PortableTests(unittest.TestCase):
    def test_self_contained_and_xss_not_literal(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bundle = make_bundle(root)
            output = root / "review.html"

            build(bundle, output)

            text = output.read_text(encoding="utf-8")

            self.assertNotIn("<script>alert(1)</script>", text)
            self.assertIn("connect-src 'none'", text)

            network_text = text.replace(
                "http://www.w3.org/2000/svg",
                "",
            )

            self.assertNotIn("https://", network_text)
            self.assertNotIn("http://", network_text)
            self.assertIn("Export decisions.json", text)

    def test_portable_export_is_session_bound(self):
        js = (
            ROOT
            / "review_workbench"
            / "portable_app.js"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "session_id:state.session.session_id",
            js,
        )
        self.assertIn(
            "decisions:[...state.decisions.values()]",
            js,
        )

    def test_exported_decision_envelope_imports(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bundle = make_bundle(root)
            decisions = root / "decisions.json"

            payload = {
                "format_version": "1.0",
                "session_id": "RS_x",
                "exported_at": "2026-09-24T00:00:00Z",
                "decisions": [
                    {
                        "unit_id": "U1",
                        "status": "KEEP_CURRENT",
                        "reviewer_note": "",
                        "waived_issue_fingerprints": [],
                    }
                ],
            }

            decisions.write_text(
                json.dumps(payload),
                encoding="utf-8",
            )

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "import_review_decisions.py"),
                    str(bundle),
                    str(decisions),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            data = load_bundle(bundle)
            saved = data["decisions"][0]

            self.assertEqual(saved["status"], "KEEP_CURRENT")
            self.assertEqual(saved["approved_target"], "safe")
            self.assertEqual(saved["revision"], 1)

    def test_legacy_bare_array_is_rejected_cleanly(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bundle = make_bundle(root)
            decisions = root / "legacy.json"

            decisions.write_text(
                json.dumps(
                    [
                        {
                            "unit_id": "U1",
                            "status": "KEEP_CURRENT",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "import_review_decisions.py"),
                    str(bundle),
                    str(decisions),
                ],
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "legacy bare decision arrays are not safe to import",
                result.stderr,
            )


if __name__ == "__main__":
    unittest.main()

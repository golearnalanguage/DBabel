import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from prepare_review_qa import prepare_units
from create_review_session import _bind_glossary_candidates
from xlsx_review_adapter import (
    apply_reviewed_xlsx,
    build_anchors,
    round_trip_verify_xlsx,
    verify_package_fidelity_xlsx,
)


class ReviewQaSelectionTests(unittest.TestCase):
    def test_translate_prefers_suggested_target(self):
        units = [
            {
                "id": "U1",
                "source": "步骤",
                "target": "步骤",
                "suggested_target": "Step",
                "_decision": "REPLACE",
                "source_language": "zh-CN",
                "target_language": "en",
            }
        ]
        prepared, receipt = prepare_units(units, "TRANSLATE")
        self.assertEqual(prepared[0]["target"], "Step")
        self.assertEqual(
            receipt["selection"][0]["selected_from"],
            "suggested_target",
        )

    def test_cross_language_identity_fails_without_protect(self):
        units = [
            {
                "id": "U1",
                "source": "步骤",
                "target": "步骤",
                "source_language": "zh-CN",
                "target_language": "en",
            }
        ]
        with self.assertRaises(ValueError):
            prepare_units(units, "TRANSLATE")

    def test_explicit_protect_identity_is_allowed(self):
        units = [
            {
                "id": "U1",
                "source": "MAX_SESSIONS",
                "target": "MAX_SESSIONS",
                "_decision": "PROTECT",
                "source_language": "zh-CN",
                "target_language": "en",
            }
        ]
        prepared, _ = prepare_units(units, "TRANSLATE")
        self.assertEqual(prepared[0]["target"], "MAX_SESSIONS")


class TerminologyBindingTests(unittest.TestCase):
    def test_glossary_candidate_binds_to_unit_and_evidence(self):
        units = [
            {
                "id": "U1",
                "source": "表空间",
                "current_target": "表空间",
                "suggested_target": "tablespace",
                "labels": [],
                "finding_refs": [],
                "qa_issue_refs": [],
                "evidence_refs": [],
                "term_refs": [],
            }
        ]
        issues = []
        _bind_glossary_candidates(
            [
                {
                    "term": "表空间",
                    "proposed_target": "tablespace",
                    "status": "DISCOVERED",
                    "evidence_refs": ["E1"],
                }
            ],
            units,
            {"E1"},
            issues,
        )
        self.assertTrue(units[0]["term_refs"])
        self.assertIn("E1", units[0]["evidence_refs"])
        self.assertEqual(issues[0]["label"], "TERM_CANDIDATE")


class XlsxRoundTripTests(unittest.TestCase):
    def test_xlsx_renames_only_anchored_tab_and_its_print_area(self):
        workbook = (
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheets><sheet name="参数配置" sheetId="1"/><sheet name="保留" sheetId="2"/></sheets>'
            '<definedNames><definedName name="_xlnm.Print_Area" localSheetId="0">'
            '参数配置!$A$1:$B$7</definedName></definedNames></workbook>'
        ).encode('utf-8')
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / 'source.xlsx'
            output = Path(td) / 'reviewed.xlsx'
            with zipfile.ZipFile(source, 'w') as zf:
                zf.writestr('xl/workbook.xml', workbook)
                zf.writestr('xl/worksheets/sheet1.xml', b'<worksheet>unchanged</worksheet>')
            unit = {'id': 'TAB1', 'location': 'xl/workbook.xml:sheet:1',
                    'current_target': '参数配置'}
            anchors = build_anchors(source, [unit])
            self.assertEqual(anchors['TAB1']['status'], 'RESOLVED')
            decisions = {'TAB1': {'status': 'USER_EDITED', 'approved_target': 'Parameter settings'}}
            self.assertEqual(apply_reviewed_xlsx(source, output, [unit], decisions, anchors), ['TAB1'])
            round_trip_verify_xlsx(output, [unit], decisions, anchors)
            verify_package_fidelity_xlsx(source, output, [unit], decisions, anchors)
            with zipfile.ZipFile(source) as before, zipfile.ZipFile(output) as after:
                text = after.read('xl/workbook.xml').decode('utf-8')
                self.assertIn('name="Parameter settings"', text)
                self.assertIn("'Parameter settings'!$A$1:$B$7", text)
                self.assertIn('name="保留"', text)
                self.assertEqual(before.read('xl/worksheets/sheet1.xml'),
                                 after.read('xl/worksheets/sheet1.xml'))

    def test_xlsx_changes_only_anchored_cell(self):
        worksheet = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/'
            'spreadsheetml/2006/main">'
            '<sheetData><row r="1">'
            '<c r="A1" t="inlineStr"><is><t>步骤</t></is></c>'
            '<c r="B1"><v>42</v></c>'
            '</row></sheetData>'
            '<dataValidations count="0"/></worksheet>'
        ).encode("utf-8")

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            source = td / "source.xlsx"
            output = td / "reviewed.xlsx"

            with zipfile.ZipFile(source, "w") as zf:
                zf.writestr(
                    "xl/worksheets/sheet1.xml",
                    worksheet,
                )
                zf.writestr(
                    "xl/drawings/drawing1.xml",
                    b"<drawing>unchanged</drawing>",
                )

            units = [
                {
                    "id": "U1",
                    "location": "xl/worksheets/sheet1.xml:A1",
                    "source": "步骤",
                    "current_target": "步骤",
                }
            ]
            anchors = build_anchors(source, units)
            self.assertEqual(
                anchors["U1"]["status"], "RESOLVED"
            )

            decisions = {
                "U1": {
                    "unit_id": "U1",
                    "status": "USER_EDITED",
                    "approved_target": "Step",
                }
            }

            changed = apply_reviewed_xlsx(
                source,
                output,
                units,
                decisions,
                anchors,
            )
            self.assertEqual(changed, ["U1"])

            round_trip_verify_xlsx(
                output,
                units,
                decisions,
                anchors,
            )
            verify_package_fidelity_xlsx(
                source,
                output,
                units,
                decisions,
                anchors,
            )

            with zipfile.ZipFile(source) as before, zipfile.ZipFile(
                output
            ) as after:
                self.assertEqual(
                    before.read("xl/drawings/drawing1.xml"),
                    after.read("xl/drawings/drawing1.xml"),
                )


class WorkbenchSourceTests(unittest.TestCase):
    def test_proposal_first_and_surface_labels_present(self):
        desktop = (
            ROOT
            / "review_workbench"
            / "static"
            / "app.js"
        ).read_text(encoding="utf-8")
        portable = (
            ROOT
            / "review_workbench"
            / "portable_app.js"
        ).read_text(encoding="utf-8")
        views = (
            ROOT
            / "review_workbench"
            / "static"
            / "workbench_views.js"
        ).read_text(encoding="utf-8")

        self.assertIn("reviewTarget", desktop)
        self.assertIn("reviewTarget", portable)
        self.assertIn("Portable Review fallback", views)
        self.assertIn("Full Local Workbench", views)


if __name__ == "__main__":
    unittest.main()

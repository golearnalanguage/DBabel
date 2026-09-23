"""Contract regressions: reject contradictory evidence, repair, and completion."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from validate_report import validate_report
from check_package import check_package


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.report = json.loads((ROOT / 'examples/audit_report.json').read_text(encoding='utf-8'))

    def rejected(self, fragment):
        errors = validate_report(self.report)
        self.assertTrue(any(fragment in e for e in errors), errors)

    def repaired(self):
        self.report['repair'] = {
            'status': 'VERIFIED', 'authorized': True, 'output_document': 'manual.revised.md',
            'changes': [{'finding_id': 'F1', 'location': 'manual.md:3',
                         'before': '同步节点', 'after': '同步点', 'status': 'APPLIED'}],
            'round_trip_qa': {'status': 'PASS', 'checks': [
                {'name': 'reopen_and_compare', 'status': 'PASS', 'note': 'Only the located term changed.'}]},
            'note': 'Synthetic repair result.'}

    def test_valid_audit(self):
        self.assertEqual(validate_report(self.report), [])

    def test_valid_repair_with_other_review_items(self):
        self.repaired()
        self.assertEqual(validate_report(self.report), [])

    def test_missing_evidence(self):
        self.report['sources'] = []
        self.rejected('dangling evidence')

    def test_duplicate_source(self):
        self.report['sources'] *= 2
        self.rejected('duplicate source')

    def test_duplicate_finding(self):
        self.report['findings'] *= 2
        self.rejected('duplicate finding')

    def test_unopened_source(self):
        self.report['sources'][0]['source_opened'] = False
        self.rejected('adequate opened evidence')

    def test_opened_snippet_is_still_not_authority(self):
        self.report['sources'][0]['source_type'] = 'search_snippet'
        self.rejected('adequate opened evidence')

    def test_mt_output_is_not_authority(self):
        self.report['sources'][0]['source_type'] = 'mt_llm_output'
        self.rejected('adequate opened evidence')

    def test_stale_source(self):
        self.report['sources'][0]['evidence_state'] = 'STALE'
        self.rejected('adequate opened evidence')

    def test_conflicting_source(self):
        self.report['sources'][0]['evidence_state'] = 'CONFLICTING'
        self.rejected('conflict requires REVIEW')

    def test_adjacent_version_cannot_support_high(self):
        self.report['sources'][0]['version_match'] = 'ADJACENT'
        self.rejected('adequate opened evidence')

    def test_adjacent_version_can_support_medium_proposal(self):
        self.report['sources'][0]['version_match'] = 'ADJACENT'
        self.report['findings'][0]['confidence'] = 'MEDIUM'
        self.assertEqual(validate_report(self.report), [])

    def test_verified_keep_needs_source(self):
        self.report['findings'][0]['decision'] = 'KEEP'
        self.report['findings'][0]['evidence_refs'] = []
        self.rejected('adequate opened evidence')

    def test_replacement_requires_wording(self):
        del self.report['findings'][0]['recommendation']
        self.rejected('recommendation')

    def test_same_wording_is_not_replacement(self):
        self.report['findings'][0]['recommendation'] = '同步节点'
        self.rejected('unchanged')

    def test_bad_date(self):
        self.report['sources'][0]['retrieved_at'] = '2026-02-30'
        self.rejected('date')

    def test_review_needs_next_action(self):
        del self.report['findings'][3]['next_action']
        self.rejected('next_action')

    def test_unresolved_items_cannot_be_completed(self):
        self.report['status'] = 'COMPLETED'
        self.rejected('resolved findings')

    def test_partial_coverage_cannot_be_full(self):
        self.report['coverage']['uninspected'] = ['speaker notes']
        self.rejected('FULL coverage')

    def test_skipped_check_cannot_pass(self):
        self.report['qa']['checks'][0]['status'] = 'NOT_RUN'
        self.rejected('performed, passing')

    def test_failed_check_cannot_pass(self):
        self.report['qa']['checks'][0]['status'] = 'FAIL'
        self.rejected('failed check')

    def test_repair_requires_authorization(self):
        self.repaired()
        self.report['repair']['authorized'] = False
        self.rejected('not authorized')

    def test_repair_requires_high_confidence(self):
        self.repaired()
        self.report['findings'][0]['confidence'] = 'MEDIUM'
        self.rejected('not eligible')

    def test_protected_literal_needs_separate_authorization(self):
        self.repaired()
        self.report['findings'][0]['protected'] = True
        self.rejected('protected literal')
        self.report['repair']['changes'][0]['literal_change_authorized'] = True
        self.assertEqual(validate_report(self.report), [])

    def test_repair_cannot_apply_review(self):
        self.repaired()
        self.report['repair']['changes'][0]['finding_id'] = 'F4'
        self.rejected('not eligible')

    def test_repair_must_match_original_span(self):
        self.repaired()
        self.report['repair']['changes'][0]['before'] = 'different source'
        self.rejected('does not match')

    def test_repair_must_match_location(self):
        self.repaired()
        self.report['repair']['changes'][0]['location'] = 'manual.md:11'
        self.rejected('does not match')

    def test_repair_needs_output(self):
        self.repaired()
        del self.report['repair']['output_document']
        self.rejected('changes, and output')

    def test_verified_repair_needs_qa(self):
        self.repaired()
        self.report['repair']['round_trip_qa']['status'] = 'NOT_RUN'
        self.rejected('passed round-trip')

    def test_proposed_repair_cannot_contain_applied_change(self):
        self.repaired()
        self.report['repair']['status'] = 'PROPOSED'
        self.rejected('contradicts applied')

    def test_failed_task_can_be_valid_report(self):
        self.repaired()
        self.report['repair']['status'] = 'FAILED'
        self.report['repair']['round_trip_qa']['status'] = 'FAIL'
        self.report['repair']['round_trip_qa']['checks'][0]['status'] = 'FAIL'
        self.report['status'] = 'FAILED'
        self.assertEqual(validate_report(self.report), [])

    def test_cli_from_other_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            proc = subprocess.run([sys.executable, str(ROOT / 'scripts/validate_report.py'),
                                   str(ROOT / 'examples/audit_report.json')], cwd=temp,
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            bad = Path(temp) / 'bad.json'
            bad.write_text('{}')
            proc = subprocess.run([sys.executable, str(ROOT / 'scripts/validate_report.py'), str(bad)],
                                  cwd=temp, capture_output=True, text=True)
            self.assertNotEqual(proc.returncode, 0)

    def test_repair_mode_cannot_skip_requested_work(self):
        self.report['mode'] = 'REPAIR'
        self.rejected('REPAIR mode')

    def test_executable_token_must_be_protected(self):
        self.report['findings'][1]['protected'] = False
        self.rejected('protected')

    def test_not_run_cannot_contain_performed_checks(self):
        self.report['qa']['status'] = 'NOT_RUN'
        self.rejected('contradicts performed')

    def test_package(self):
        self.assertEqual(check_package(), [])


if __name__ == '__main__':
    unittest.main()

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCRIPTS=ROOT/'scripts'
if str(SCRIPTS) not in sys.path:sys.path.insert(0,str(SCRIPTS))

from review_model import (
    default_decision, deterministic_issue_to_review, evaluate_export_gate,
    normalize_decision, review_issue_fingerprint, validate_against_schema,
    write_json, write_jsonl, load_bundle
)

class ReviewModelTests(unittest.TestCase):
    def test_fingerprint_ignores_transient_issue_id(self):
        a={'unit_id':'U1','kind':'DETERMINISTIC','label':'NUMBER_INTEGRITY','classification':'POTENTIAL_ISSUE','source_items':['1'],'target_items':['2'],'suggestion':None}
        b=dict(a);b['id']='Q9999'
        self.assertEqual(review_issue_fingerprint(a),review_issue_fingerprint(b))

    def test_deterministic_issue_stays_potential_issue(self):
        r=deterministic_issue_to_review({'id':'Q0001','unit_id':'U1','check_id':'NUMBER_INTEGRITY','classification':'POTENTIAL_ISSUE','severity':'ERROR','message':'m','source_items':['1'],'target_items':['2']})
        self.assertEqual(r['classification'],'POTENTIAL_ISSUE')
        self.assertTrue(r['blocking'])

    def test_decision_contract_requires_waiver_reason(self):
        schema=ROOT/'schemas'/'review_decision.schema.json'
        d=default_decision('U1');d.update({'status':'WAIVED','approved_target':'x'})
        self.assertTrue(validate_against_schema(d,schema))
        d['waiver_reason']='customer requirement'
        self.assertEqual(validate_against_schema(d,schema),[])

    def test_normalize_user_edit_invalidates_recheck(self):
        unit={'id':'U1','current_target':'old'}
        prev=default_decision('U1');prev['recheck']={'status':'PASS','error_count':0,'warning_count':0,'issue_fingerprints':[]}
        d=normalize_decision(unit,{'status':'USER_EDITED','approved_target':'new'},prev)
        self.assertEqual(d['recheck']['status'],'NOT_RUN')

    def test_accept_rejects_empty_suggestion(self):
        for target in [None, '', '   ']:
            with self.assertRaises(ValueError):
                normalize_decision({'id':'U1','current_target':'original','suggested_target':target}, {'status':'ACCEPT_SUGGESTION'}, default_decision('U1'))

    def test_export_gate_blocks_unreviewed(self):
        with tempfile.TemporaryDirectory() as td:
            b=Path(td)/'x.dbreview';b.mkdir()
            session={'format_version':'1.0','session_id':'RS_x','created_at':'2026-01-01T00:00:00Z','dbabel_version':'1.5.0','mode':'BILINGUAL_REVIEW','bundle_files':{'units':'units.jsonl','issues':'issues.json','evidence':'evidence.json','decisions':'decisions.json','events':'events.jsonl','anchors':'anchors.json'},'original':{'filename':'x.txt','format':'review-data','sha256':'0'*64},'counts':{'units':1,'issues':0,'evidence':0},'export_policy':{'require_all_confirmed':True,'block_unwaived_errors':True,'require_user_edit_recheck':True,'never_overwrite_original':True}}
            write_json(b/'session.json',session);write_jsonl(b/'units.jsonl',[{'id':'U1','location':'u','source':'s','current_target':'t','labels':[],'finding_refs':[],'qa_issue_refs':[],'evidence_refs':[],'requires_confirmation':True}]);write_json(b/'issues.json',[]);write_json(b/'evidence.json',[]);write_json(b/'decisions.json',[default_decision('U1')]);write_json(b/'anchors.json',{});(b/'events.jsonl').write_text('')
            receipt=evaluate_export_gate(load_bundle(b))
            self.assertEqual(receipt['status'],'BLOCKED')
            self.assertIn('U1 is UNREVIEWED',receipt['blockers'])

if __name__=='__main__':unittest.main()

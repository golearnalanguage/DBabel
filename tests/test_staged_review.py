import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from test_review_end_to_end import make_docx, qa_pass
from review_model import load_bundle, normalize_decision, save_decisions, evaluate_export_gate, validate_against_schema
from export_reviewed_document import export_bundle
from docx_review_adapter import extract_paragraphs
from build_post_review_report import build_report
from route_resources import build_plan
from test_resource_router import make_context

ROOT = Path(__file__).resolve().parents[1]


class StagedReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.original = self.root/'original.docx'
        make_docx(self.original, ['Original first.', 'Original pending.'])
        units = self.root/'units.jsonl'
        units.write_text('\n'.join(json.dumps({'id':f'U{i+1}', 'source':text, 'target':text, 'location':f'docx:word/document.xml:p={i}', 'source_language':'en', 'target_language':'en'}) for i,text in enumerate(['Original first.', 'Original pending.']))+'\n')
        self.bundle = self.root/'review.dbreview'
        subprocess.run([sys.executable,str(ROOT/'scripts/create_review_session.py'),str(units),'--original',str(self.original),'--output',str(self.bundle)],check=True,capture_output=True)

    def tearDown(self):
        self.temp.cleanup()

    def approve_first(self):
        data=load_bundle(self.bundle)
        decision=normalize_decision(data['units'][0],{'status':'USER_EDITED','approved_target':'Reviewed first.'},data['decisions'][0])
        save_decisions(self.bundle,[decision,data['decisions'][1]])

    def test_checkpoint_preserves_pending_and_does_not_approve_it(self):
        self.approve_first()
        out=self.root/'checkpoint.docx'
        receipt=export_bundle(self.bundle,ROOT,self.original,out,qa_runner=qa_pass,export_mode='CHECKPOINT')
        self.assertEqual(receipt['status'],'VERIFIED')
        self.assertEqual([p['text'] for p in extract_paragraphs(out)],['Reviewed first.','Original pending.'])
        self.assertEqual(receipt['review_scope']['unreviewed_unit_ids'],['U2'])
        self.assertFalse(receipt['review_scope']['complete'])
        self.assertEqual(load_bundle(self.bundle)['decisions_by_id']['U2']['status'],'UNREVIEWED')
        self.assertEqual(validate_against_schema(receipt,ROOT/'schemas/export_receipt.schema.json'),[])
        self.assertEqual(receipt['qa_summary']['units_checked'],1)

    def test_final_still_blocks_pending(self):
        self.approve_first()
        result=export_bundle(self.bundle,ROOT,self.original,self.root/'final.docx',qa_runner=qa_pass)
        self.assertEqual(result['status'],'BLOCKED')
        self.assertFalse((self.root/'final.docx').exists())

    def test_empty_checkpoint_is_blocked(self):
        result=evaluate_export_gate(load_bundle(self.bundle),export_mode='CHECKPOINT')
        self.assertEqual(result['status'],'BLOCKED')

    def test_invalid_mode_fails_closed(self):
        with self.assertRaises(ValueError):evaluate_export_gate(load_bundle(self.bundle),export_mode='ALL_APPROVED')

    def test_checkpoint_rechecks_edits_and_blocks_new_error(self):
        self.approve_first()
        def qa_fail(*args):return {'issues':[{'id':'Q1','label':'PROTECTED_LITERAL','severity':'ERROR','blocking':True,'fingerprint':'a'*64}]}
        result=export_bundle(self.bundle,ROOT,self.original,self.root/'bad.docx',qa_runner=qa_fail,export_mode='CHECKPOINT')
        self.assertEqual(result['status'],'BLOCKED')
        self.assertFalse((self.root/'bad.docx').exists())

    def test_checkpoint_still_checks_original_hash(self):
        self.approve_first();make_docx(self.original,['Changed outside review.'])
        result=export_bundle(self.bundle,ROOT,self.original,self.root/'bad.docx',qa_runner=qa_pass,export_mode='CHECKPOINT')
        self.assertEqual(result['status'],'BLOCKED')

    def test_handoff_is_advisory_revision_bound_and_non_mutating(self):
        self.approve_first();before=(self.bundle/'decisions.json').read_bytes()
        report=build_report(load_bundle(self.bundle))
        self.assertEqual(report['agent_review_status'],'NOT_RUN')
        self.assertEqual(report['units'][0]['priority'],'HUMAN_EDIT')
        self.assertEqual(report['units'][0]['reviewed_target'],'Reviewed first.')
        self.assertEqual(len(report['units'][0]['target_sha256']),64)
        self.assertEqual(before,(self.bundle/'decisions.json').read_bytes())
        data=load_bundle(self.bundle)
        d=normalize_decision(data['units'][0],{'status':'USER_EDITED','approved_target':'New revision.'},data['decisions'][0]);save_decisions(self.bundle,[d,data['decisions'][1]])
        new=build_report(load_bundle(self.bundle))
        self.assertNotEqual(report['decision_digest'],new['decision_digest'])
        self.assertNotEqual(report['units'][0]['target_sha256'],new['units'][0]['target_sha256'])

    def test_route_loads_only_matching_independent_cases(self):
        context=make_context();context['risk_tags']=['execution_scope']
        plan=build_plan(context)
        self.assertEqual(plan['example_files'],['examples/cases/context/A2.zh-CN.md'])
        self.assertIn(plan['example_files'][0],plan['load_now'])
        self.assertFalse(any('technical_translation_review_examples' in p for p in plan['load_now']))

    def test_checkpoint_rejects_overlap_with_pending_anchor(self):
        self.approve_first()
        path=self.bundle/'anchors.json'
        anchors=json.loads(path.read_text());anchors['U2']=dict(anchors['U1'])
        path.write_text(json.dumps(anchors))
        out=self.root/'overlap.docx'
        result=export_bundle(self.bundle,ROOT,self.original,out,qa_runner=qa_pass,export_mode='CHECKPOINT')
        self.assertEqual(result['status'],'FAILED')
        self.assertFalse(out.exists())
        self.assertTrue(any('overlaps' in message for message in result['blockers']))

    def test_server_checkpoint_names_receipts_and_keeps_final_gate(self):
        import http.client
        import threading
        from http.server import ThreadingHTTPServer
        from start_review_workbench import Handler, WorkbenchState
        self.approve_first()
        state=WorkbenchState(self.bundle,ROOT,'synthetic-token',self.original,self.root/'delivery.docx')
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.state=state
        state.origin='http://127.0.0.1:'+str(server.server_port)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def request(method,path,body=None):
            connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=10)
            connection.request(method,path,json.dumps(body) if body is not None else None,{'X-DBabel-Session':'synthetic-token','Content-Type':'application/json'})
            response=connection.getresponse();data=json.loads(response.read());connection.close()
            return response.status,data
        try:
            code,report=request('GET','/api/post-review-report')
            self.assertEqual(code,200);self.assertEqual(report['agent_review_status'],'NOT_RUN')
            _,gate=request('POST','/api/export-gate',{'export_mode':'FINAL'})
            self.assertEqual(gate['status'],'BLOCKED')
            _,gate=request('POST','/api/export-gate',{'export_mode':'CHECKPOINT'})
            self.assertEqual(gate['status'],'AUTHORIZED')
            self.assertIn('review_decisions',gate)
            for i in (1,2):
                code,receipt=request('POST','/api/export',{'export_mode':'CHECKPOINT'})
                self.assertEqual(code,200);self.assertEqual(receipt['status'],'VERIFIED')
                self.assertTrue((self.root/f'delivery.checkpoint-{i}.docx').is_file())
                self.assertTrue((self.root/f'delivery.checkpoint-{i}.receipt.json').is_file())
            self.assertFalse((self.root/'delivery.docx').exists())
            self.assertEqual(load_bundle(self.bundle)['decisions_by_id']['U2']['status'],'UNREVIEWED')
        finally:
            server.shutdown();server.server_close();thread.join()

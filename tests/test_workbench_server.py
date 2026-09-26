import http.client
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer

ROOT=Path(__file__).resolve().parents[1];SCRIPTS=ROOT/'scripts'
if str(SCRIPTS) not in sys.path:sys.path.insert(0,str(SCRIPTS))
from review_model import default_decision,write_json,write_jsonl
from start_review_workbench import Handler,WorkbenchState


def make_fake_repo(root):
    (root/'scripts').mkdir(parents=True);(root/'config').mkdir(parents=True)
    (root/'config'/'deterministic_qa.yaml').write_text('version: 1.5.0\n')
    (root/'scripts'/'check_bilingual_integrity.py').write_text('''\ndef load_config(path): return {}\ndef _load_glossary(path): return None\ndef run_qa(units, config, glossary): return {"summary":{"units_checked":len(units),"error_count":0,"warning_count":0},"checks_run":[],"issues":[]}\n''')

def make_bundle(root):
    b=root/'x.dbreview';b.mkdir();session={'format_version':'1.0','session_id':'RS_x','created_at':'2026-01-01T00:00:00Z','dbabel_version':'1.5.0','mode':'BILINGUAL_REVIEW','title':'Server test','bundle_files':{'units':'units.jsonl','issues':'issues.json','evidence':'evidence.json','decisions':'decisions.json','events':'events.jsonl','anchors':'anchors.json'},'original':{'filename':'x.jsonl','format':'review-data','sha256':'0'*64},'counts':{'units':1,'issues':0,'evidence':0},'export_policy':{'require_all_confirmed':True,'block_unwaived_errors':True,'require_user_edit_recheck':True,'never_overwrite_original':True}}
    write_json(b/'session.json',session);write_jsonl(b/'units.jsonl',[{'id':'U1','location':'u','source':'s','current_target':'t','labels':[],'finding_refs':[],'qa_issue_refs':[],'evidence_refs':[],'requires_confirmation':True}]);write_json(b/'issues.json',[]);write_json(b/'evidence.json',[]);write_json(b/'decisions.json',[default_decision('U1')]);write_json(b/'anchors.json',{});(b/'events.jsonl').write_text('');return b

class ServerTests(unittest.TestCase):
    def setUp(self):
        self.td=tempfile.TemporaryDirectory();root=Path(self.td.name);self.bundle=make_bundle(root);self.repo=root/'repo';make_fake_repo(self.repo);self.token='secret-token'
        state=WorkbenchState(self.bundle,self.repo,self.token);self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.state=state;host,port=self.server.server_address[:2];state.origin=f'http://{host}:{port}';self.origin=state.origin;self.port=port
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.td.cleanup()
    def req(self,method,path,body=None,headers=None):
        c=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5);payload=None if body is None else json.dumps(body);h=headers or {};h.setdefault('Content-Type','application/json');c.request(method,path,payload,headers=h);r=c.getresponse();raw=r.read();c.close();return r.status,json.loads(raw.decode()) if raw else None
    def test_runtime_is_served_as_one_ordered_dependency_bundle(self):
        c=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
        c.request('GET','/app.js');r=c.getresponse();source=r.read().decode();c.close()
        self.assertEqual(r.status,200)
        self.assertLess(source.index('window.dbabelI18n='),source.index('window.installExchange ='))
        self.assertLess(source.index('window.installWorkbenchViews ='),source.index('const state={token:'))

    def test_api_requires_token(self):
        status,_=self.req('GET','/api/bootstrap');self.assertEqual(status,403)
    def test_wrong_origin_rejected(self):
        status,_=self.req('GET','/api/bootstrap',headers={'X-DBabel-Session':self.token,'Origin':'https://evil.example'});self.assertEqual(status,403)
    def test_save_decision_and_gate(self):
        headers={'X-DBabel-Session':self.token,'Origin':self.origin}
        status,body=self.req('PUT','/api/decisions/U1',{'status':'KEEP_CURRENT'},headers);self.assertEqual(status,200);self.assertEqual(body['decision']['status'],'KEEP_CURRENT');self.assertEqual(body['decision']['recheck']['status'],'PASS')
        status,gate=self.req('POST','/api/export-gate',{},headers);self.assertEqual(status,200);self.assertEqual(gate['status'],'AUTHORIZED')


    def test_bulk_decisions_fail_atomically_and_preserve_notes(self):
        headers={
            'X-DBabel-Session':self.token,
            'Origin':self.origin,
        }

        status,_=self.req(
            'POST',
            '/api/decisions/bulk',
            {
                'status':'KEEP_CURRENT',
                'unit_ids':['U1','MISSING'],
            },
            headers,
        )

        self.assertEqual(status,400)

        status,bootstrap=self.req(
            'GET',
            '/api/bootstrap',
            headers=headers,
        )

        self.assertEqual(status,200)

        self.assertEqual(
            bootstrap['decisions'][0]['status'],
            'UNREVIEWED',
        )

        status,_=self.req(
            'PUT',
            '/api/decisions/U1',
            {
                'status':'BLOCKED',
                'reviewer_note':'preserve this note',
            },
            headers,
        )

        self.assertEqual(status,200)

        status,result=self.req(
            'POST',
            '/api/decisions/bulk',
            {
                'status':'KEEP_CURRENT',
                'unit_ids':['U1'],
            },
            headers,
        )

        self.assertEqual(status,200)

        decision=result['results'][0]['decision']

        self.assertEqual(
            decision['status'],
            'KEEP_CURRENT',
        )

        self.assertEqual(
            decision['reviewer_note'],
            'preserve this note',
        )

        self.assertEqual(
            decision['recheck']['status'],
            'PASS',
        )

    def test_review_only_results_preserve_pending_and_accept_all_formats(self):
        headers={'X-DBabel-Session':self.token,'Origin':self.origin}
        for fmt in ['json','csv','tsv','md','html','txt']:
            status,result=self.req('POST','/api/results',{'format':fmt},headers)
            self.assertEqual(status,200)
            self.assertTrue(result['content'])
            self.assertIn('UNREVIEWED',result['content'])
        status,_=self.req('POST','/api/results',{'format':[]},headers)
        self.assertEqual(status,400)

    def test_upload_inspect_create_and_reject_stale_session_token(self):
        import base64
        headers={'X-DBabel-Session':self.token,'Origin':self.origin}
        payload={'name':'source.txt','content_base64':base64.b64encode('甲\n乙'.encode()).decode()}
        status,info=self.req('POST','/api/intake/inspect',{'source':payload},headers)
        self.assertEqual(status,200);self.assertEqual(info['segment_count'],2)
        old_bundle=self.server.state.bundle
        status,result=self.req('POST','/api/intake/create',{'source':payload,'source_language':'zh-CN','target_languages':['en','ja']},headers)
        self.assertEqual(status,200)
        self.assertTrue(old_bundle.exists())
        status,_=self.req('GET','/api/bootstrap',headers=headers)
        self.assertEqual(status,403)
        headers['X-DBabel-Session']=result['token']
        status,current=self.req('GET','/api/bootstrap',headers=headers)
        self.assertEqual(status,200);self.assertEqual(len(current['units']),4)
        self.assertFalse(current['export_available'])

    def test_glossary_upload_validates_before_replacing_saved_resource(self):
        import base64
        headers={'X-DBabel-Session':self.token,'Origin':self.origin}
        content=(ROOT/'templates/project_glossary.csv').read_bytes()
        status,result=self.req('POST','/api/glossary',{'file':{'name':'terms.csv','content_base64':base64.b64encode(content).decode()}},headers)
        self.assertEqual(status,200)
        saved=self.server.state.glossary
        before=saved.read_bytes()
        status,_=self.req('POST','/api/glossary',{'file':{'name':'bad.json','content_base64':base64.b64encode(b'{}').decode()}},headers)
        self.assertEqual(status,400);self.assertEqual(saved.read_bytes(),before)
        status,_=self.req('GET','/api/glossary',headers=headers)
        self.assertEqual(status,200)


if __name__=='__main__':unittest.main()

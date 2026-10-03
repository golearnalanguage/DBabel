import http.client
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer

ROOT=Path(__file__).resolve().parents[1];SCRIPTS=ROOT/'scripts'
if str(SCRIPTS) not in sys.path:sys.path.insert(0,str(SCRIPTS))
from review_model import default_decision,write_json,write_jsonl
from start_review_workbench import Handler,WorkbenchState
from review_chat import load_messages


class StandaloneLauncherTests(unittest.TestCase):
    def test_server_imports_from_another_working_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            process = subprocess.run(
                [sys.executable, str(SCRIPTS / 'start_review_workbench.py'), '--help'],
                cwd=directory, capture_output=True, text=True, timeout=15,
            )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn('--provider-config', process.stdout)


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
        self.memory_env=patch.dict(os.environ, {'DBABEL_TRANSLATION_MEMORY': str(root/'memory.sqlite3'),
                                              'DBABEL_GENERAL_TERMS_SETTINGS': str(root/'terms.json')})
        self.memory_env.start()
        state=WorkbenchState(self.bundle,self.repo,self.token);self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.state=state;host,port=self.server.server_address[:2];state.origin=f'http://{host}:{port}';self.origin=state.origin;self.port=port
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.memory_env.stop();self.td.cleanup()
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
    def test_local_reference_and_memory_endpoints(self):
        headers={'X-DBabel-Session':self.token,'Origin':self.origin}
        status,terms=self.req('GET','/api/general-terms',headers=headers)
        self.assertEqual(status,200)
        self.assertFalse(terms['enabled'])
        self.assertGreater(len(terms['entries']),10)
        status,updated=self.req('POST','/api/general-terms',{'enabled':True},headers)
        self.assertEqual(status,200)
        self.assertTrue(updated['enabled'])
        status,template=self.req('GET','/api/glossary/template',headers=headers)
        self.assertEqual(status,200)
        self.assertIn('source_term',template['content'])
        status,memory=self.req('GET','/api/translation-memory',headers=headers)
        self.assertEqual(status,200)
        self.assertEqual(memory['count'],0)
    def test_translation_memory_can_be_edited_exported_and_deleted(self):
        unit=json.loads((self.bundle/'units.jsonl').read_text().splitlines()[0])
        unit.update(source_language='zh-CN',target_language='en')
        write_jsonl(self.bundle/'units.jsonl',[unit])
        headers={'X-DBabel-Session':self.token,'Origin':self.origin}
        status,result=self.req('PUT','/api/decisions/U1',{'status':'KEEP_CURRENT'},headers)
        self.assertEqual(status,200,result)
        status,memory=self.req('GET','/api/translation-memory',headers=headers)
        self.assertEqual(memory['count'],1)
        entry=memory['entries'][0]
        self.assertEqual(entry['target'],'t')
        status,updated=self.req('POST','/api/translation-memory/edit',
                                {'id':entry['id'],'target':'new target'},headers)
        self.assertEqual(status,200,updated)
        self.assertEqual(updated['entries'][0]['target'],'new target')
        status,exported=self.req('GET','/api/translation-memory/export',headers=headers)
        self.assertEqual(status,200)
        self.assertEqual(exported['entries'][0]['target'],'new target')
        self.assertTrue((Path(self.td.name)/'memory.backup.sqlite3').exists())
        status,deleted=self.req('POST','/api/translation-memory/delete',{'id':entry['id']},headers)
        self.assertEqual(status,200)
        self.assertEqual(deleted['count'],0)
    def test_chat_uses_selected_unit_and_survives_reopening(self):
        class FakeProvider:
            def generate(self, request):
                self.request=request
                return type('Response',(),{'text':'The source and target need a terminology check.'})()
        provider=FakeProvider()
        self.server.state.chat_provider=provider
        headers={'X-DBabel-Session':self.token,'Origin':self.origin}
        status,result=self.req('POST','/api/chat',{'unit_id':'U1','message':'Why this wording?'},headers)
        self.assertEqual(status,200)
        self.assertEqual(result['answer']['role'],'assistant')
        self.assertIn('"source": "s"',provider.request.user)
        self.assertEqual(len(load_messages(self.bundle)),2)
        status,history=self.req('GET','/api/chat',headers=headers)
        self.assertEqual(status,200)
        self.assertEqual(history['messages'][1]['content'],result['answer']['content'])
        self.assertEqual(len(json.loads((self.bundle/'chat.backup.json').read_text())),2)
        status,_=self.req('POST','/api/chat',{'unit_id':'MISSING','message':'Why?'},headers)
        self.assertEqual(status,400)
    def test_chat_accepts_document_attachment_and_keeps_local_copy(self):
        import base64
        class FakeProvider:
            def generate(self, request):
                self.request=request
                return type('Response',(),{'text':'The attached guidance says to retain the name.'})()
        provider=FakeProvider();self.server.state.chat_provider=provider
        headers={'X-DBabel-Session':self.token,'Origin':self.origin}
        attachment={'name':'guidance.txt','content_base64':base64.b64encode('Keep XFS unchanged.\n'.encode()).decode()}
        status,result=self.req('POST','/api/chat',{'unit_id':'U1','message':'Apply this guidance?',
                                                   'attachments':[attachment]},headers)
        self.assertEqual(status,200)
        self.assertIn('Keep XFS unchanged.',provider.request.user)
        saved=result['question']['attachments'][0]
        self.assertTrue((self.bundle/saved['file']).is_file())
        self.assertEqual((self.bundle/saved['file']).read_text(),'Keep XFS unchanged.\n')
    def test_workspace_position_is_saved_for_reopen(self):
        headers={'X-DBabel-Session':self.token,'Origin':self.origin}
        draft={'target':'Unconfirmed edited text','note':'Check this term','editing':True}
        position={'selected':'U1','page':0,'page_size':50,'view':'Review',
                  'scroll_top':183,'drafts':{'U1':draft}}
        status,result=self.req('PUT','/api/ui-state',position,headers)
        self.assertEqual(status,200)
        self.assertEqual(result['scroll_top'],183)
        status,reloaded=self.req('GET','/api/ui-state',headers=headers)
        self.assertEqual(status,200)
        self.assertEqual(reloaded['selected'],'U1')
        self.assertEqual(reloaded['drafts']['U1'],draft)
        self.assertEqual(json.loads((self.bundle/'ui_state.backup.json').read_text())['scroll_top'],183)
        status,_=self.req('PUT','/api/ui-state',{**position,'selected':'MISSING'},headers)
        self.assertEqual(status,400)
        status,_=self.req('PUT','/api/ui-state',{**position,'drafts':{'MISSING':draft}},headers)
        self.assertEqual(status,400)

    def test_chat_provider_can_be_connected_after_session_opens(self):
        headers={'X-DBabel-Session':self.token,'Origin':self.origin}
        status,chat=self.req('GET','/api/chat',headers=headers)
        self.assertEqual(status,200)
        self.assertFalse(chat['available'])
        config={'provider':'openai-compatible','base_url':'http://127.0.0.1:9090/v1',
                'api_key_env':'DBABEL_TEST_KEY','model':'local-test',
                'timeout_seconds':120,'max_response_bytes':2000000}
        status,connected=self.req('POST','/api/chat/provider',
                                  {'config':config,'key':'local-test-token'},headers)
        self.assertEqual(status,200,connected)
        self.assertTrue(connected['available'])
        self.assertEqual(self.server.state.chat_provider.config.model,'local-test')
        status,chat=self.req('GET','/api/chat',headers=headers)
        self.assertTrue(chat['available'])
        self.assertNotIn('key',chat)
        status,_=self.req('POST','/api/chat/provider',
                          {'config':config,'key':'new-token'})
        self.assertEqual(status,403)
    def test_one_review_updates_exact_duplicate_but_keeps_both_rows(self):
        original=json.loads((self.bundle/'units.jsonl').read_text())
        duplicate={**original,'id':'U2','location':'another location'}
        write_jsonl(self.bundle/'units.jsonl',[original,duplicate])
        write_json(self.bundle/'decisions.json',[default_decision('U1'),default_decision('U2')])
        headers={'X-DBabel-Session':self.token,'Origin':self.origin}
        status,result=self.req('PUT','/api/decisions/U1',{'status':'KEEP_CURRENT'},headers)
        self.assertEqual(status,200)
        self.assertEqual(len(result['linked_decisions']),1)
        status,bootstrap=self.req('GET','/api/bootstrap',headers=headers)
        self.assertEqual(len(bootstrap['units']),2)
        self.assertEqual([d['status'] for d in bootstrap['decisions']],['KEEP_CURRENT','KEEP_CURRENT'])
    def test_wrong_origin_rejected(self):
        status,_=self.req('GET','/api/bootstrap',headers={'X-DBabel-Session':self.token,'Origin':'https://evil.example'});self.assertEqual(status,403)
    def test_save_decision_and_gate(self):
        headers={'X-DBabel-Session':self.token,'Origin':self.origin}
        status,body=self.req('PUT','/api/decisions/U1',{'status':'KEEP_CURRENT'},headers);self.assertEqual(status,200);self.assertEqual(body['decision']['status'],'KEEP_CURRENT');self.assertEqual(body['decision']['recheck']['status'],'PASS')
        status,gate=self.req('POST','/api/export-gate',{},headers);self.assertEqual(status,200);self.assertEqual(gate['status'],'AUTHORIZED')
        self.assertEqual(json.loads((self.bundle/'decisions.backup.json').read_text())[0]['status'],'KEEP_CURRENT')

    def test_rejection_memory_survives_reopen_and_can_be_removed(self):
        unit=json.loads((self.bundle/'units.jsonl').read_text().splitlines()[0])
        unit.update(source_language='zh-CN',target_language='en',suggested_target='Wrong term')
        write_jsonl(self.bundle/'units.jsonl',[unit])
        headers={'X-DBabel-Session':self.token,'Origin':self.origin}
        status,result=self.req('PUT','/api/decisions/U1',
            {'status':'BLOCKED','rejection_reason':'This term changes the meaning.'},headers)
        self.assertEqual(status,200,result)
        self.assertEqual(result['decision']['status'],'BLOCKED')
        self.assertEqual(result['rejection_memory']['rejected_target'],'Wrong term')
        self.assertEqual(result['rejection_memory']['scope'],'TERM')
        status,remembered=self.req('GET','/api/translation-memory',headers=headers)
        self.assertEqual(status,200)
        self.assertEqual(remembered['count'],1)
        self.assertEqual(remembered['entries'][0]['kind'],'REJECTED')
        status,memory=self.req('GET','/api/rejection-memory',headers=headers)
        self.assertEqual(status,200)
        self.assertEqual(memory['records'][0]['source'],'s')
        self.assertEqual(json.loads((self.bundle/'rejected-translations.backup.json').read_text()),memory['records'])
        status,removed=self.req('POST','/api/rejection-memory/remove',
            {'id':memory['records'][0]['id']},headers)
        self.assertEqual(status,200)
        self.assertEqual(removed['records'],[])
        status,remembered=self.req('GET','/api/translation-memory',headers=headers)
        self.assertEqual(remembered['count'],0)

    def test_bulk_accept_requires_real_suggestions_and_rechecks(self):
        headers={'X-DBabel-Session':self.token,'Origin':self.origin}
        status,result=self.req('POST','/api/decisions/bulk',
            {'status':'ACCEPT_SUGGESTION','unit_ids':['U1']},headers)
        self.assertEqual(status,400)
        unit=json.loads((self.bundle/'units.jsonl').read_text().splitlines()[0])
        unit['suggested_target']='Proposed translation'
        write_jsonl(self.bundle/'units.jsonl',[unit])
        status,result=self.req('POST','/api/decisions/bulk',
            {'status':'ACCEPT_SUGGESTION','unit_ids':['U1']},headers)
        self.assertEqual(status,200,result)
        decision=result['results'][0]['decision']
        self.assertEqual(decision['approved_target'],'Proposed translation')
        self.assertEqual(decision['recheck']['status'],'PASS')


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
            self.assertEqual(result['filename'],'Review - x.'+fmt)
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
        self.assertEqual(info['local_precheck']['extracted_segments'],2)
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

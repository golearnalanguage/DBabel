"""Synthetic long-document pipeline through a real local Chat Completions gateway."""
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from runtime.orchestrator import RuntimeOrchestrator, OrchestrationError
from runtime.translation import TranslationLimits
from runtime.semantic_adjudication import SemanticLimits
from review_model import load_bundle, normalize_decision, save_decisions
from export_reviewed_document import export_bundle

ROOT=Path(__file__).resolve().parents[1]


class GatewayWorkflowTests(unittest.TestCase):
    def test_long_translation_semantic_quota_resume_and_native_draft(self):
        calls={'TRANSLATION':[], 'ADJUDICATION':[]};failed=[False]
        class Gateway(BaseHTTPRequestHandler):
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                payload=json.loads(body['messages'][1]['content'])
                stage='ADJUDICATION' if payload['task']=='DBabel semantic risk adjudication' else 'TRANSLATION'
                units=payload['units'];calls[stage].append([u['id'] for u in units])
                if len(units)>5:
                    self.send_response(504);self.end_headers();self.wfile.write(b'{"error":{"message":"synthetic idle timeout"}}');return
                if stage=='ADJUDICATION' and len(calls[stage])==2 and not failed[0]:
                    failed[0]=True;self.send_response(402);self.end_headers();self.wfile.write(b'{"error":{"message":"synthetic quota exhausted"}}');return
                rows=[]
                for u in units:
                    rows.append({'id':u['id'],'outcome':'NO_FINDING','classification':None,'reason':'Synthetic protocol fixture only.','next_action':''}
                        if stage=='ADJUDICATION' else {'id':u['id'],'suggested_target':'Check the database configuration. Confirm that the environment meets the documented requirements. Preserve the existing files and record the result before continuing. This is a synthetic workflow fixture.',
                            'proposal_decision':'REPLACE','reason':'Synthetic fixture for transport and preservation checks, not a quality evaluation.'})
                answer=json.dumps({'units':rows})
                self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
                for text in [answer[:len(answer)//2],answer[len(answer)//2:]]:
                    data={'choices':[{'index':0,'delta':{'content':text},'finish_reason':None}]}
                    self.wfile.write(('data: '+json.dumps(data)+'\n\n').encode())
                self.wfile.write(b'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Gateway)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        try:
            with tempfile.TemporaryDirectory() as td:
                root=Path(td);source=root/'long-manual.txt'
                paragraph='配置数据库之前，应当检查环境是否满足要求。保留现有文件，确认已有配置，记录检查结果后继续后续步骤。对于已有的运行环境，不得遗漏前置检查和必要的确认。'
                source.write_text('\n\n'.join(chr(0x4e00+i)+paragraph*4 for i in range(128))+'\n',encoding='utf-8')
                original=source.read_bytes();config=root/'provider.json'
                settings={'provider':'openai-compatible','base_url':f'http://127.0.0.1:{server.server_port}/v1/chat/completions','model':'newapi-synthetic','api_key_env':'GATEWAY_TEST_KEY','stream':True,'timeout_seconds':120}
                config.write_text(json.dumps(settings))
                orchestrator=RuntimeOrchestrator(workspace_root=root/'runs')
                args=dict(source=source,source_language='zh-CN',target_language='en',provider_config_path=config,
                    default_text_role='PROSE',translation_limits=TranslationLimits(max_units_per_batch=10),semantic_limits=SemanticLimits(max_units_per_batch=5))
                with patch.dict(os.environ,{'GATEWAY_TEST_KEY':'synthetic','DBABEL_TRANSLATION_MEMORY':str(root/'memory.sqlite3'),'DBABEL_REJECTION_MEMORY':''}),patch('providers.openai_compatible.time.sleep'):
                    with self.assertRaisesRegex(OrchestrationError,'402'):orchestrator.run_translation_to_review(**args)
                    run=next((root/'runs').glob('RUN_*'));before=len(calls['TRANSLATION']);saved=calls['ADJUDICATION'][0]
                    settings.update(timeout_seconds=300,proxy_mode='none',temperature_mode='omit');config.write_text(json.dumps(settings))
                    result=orchestrator.run_translation_to_review(**args,resume_run=run)
                    self.assertEqual(result['status'],'READY_FOR_HUMAN_REVIEW')
                    self.assertEqual(len(calls['TRANSLATION']),before)
                    self.assertNotIn(saved,calls['ADJUDICATION'][2:])
                    bundle=Path(result['artifacts']['review_bundle']['path']);data=load_bundle(bundle)
                    self.assertEqual(len(data['units']),128)
                    edited=normalize_decision(data['units'][0],{'status':'USER_EDITED','approved_target':'Human reviewed first paragraph.'},data['decisions'][0])
                    save_decisions(bundle,[edited]+data['decisions'][1:])
                    output=root/'translated.txt';receipt=export_bundle(bundle,ROOT,source,output,export_mode='DRAFT')
                    self.assertEqual(receipt['status'],'DRAFT_EXPORTED')
                    text=output.read_text();self.assertTrue(text.startswith('Human reviewed first paragraph.'))
                    self.assertEqual(text.count('synthetic workflow fixture'),127)
                    self.assertEqual(text.count('\n\n'),127)
                    self.assertEqual(source.read_bytes(),original)
                    self.assertEqual(sum(d['status']=='UNREVIEWED' for d in load_bundle(bundle)['decisions']),127)
        finally:server.shutdown();server.server_close();worker.join()

if __name__=='__main__':unittest.main()

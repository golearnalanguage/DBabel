"""Wire-level gateway regressions; no real credentials or paid service required."""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from providers.base import ProviderError, ProviderResponseInterrupted, ProviderTransientError
from providers.openai_compatible import OpenAICompatibleProvider
from providers.protocol import decode_response
from runtime.models import GenerationRequest, GenerationResponse, ProviderConfig
from runtime.translation import translate_units, TranslationLimits

REQUEST = GenerationRequest(system='Return a complete answer.', user='Translate the task.')


def event(data):
    return 'data: ' + json.dumps(data, ensure_ascii=False) + '\r\n\r\n'


def chunk(text=None, finish=None):
    return {'choices': [{'index': 0, 'delta': {'content': text}, 'finish_reason': finish}]}


class CompatibilityTests(unittest.TestCase):
    def provider(self, transport, **kwargs):
        return OpenAICompatibleProvider(ProviderConfig('openai-compatible', 'https://gateway.example/v1',
            'KEY', 'glm-5.3', **kwargs), environ={'KEY':'synthetic-private-key'}, transport=transport)

    def test_sse_heartbeats_utf8_multiline_and_usage(self):
        raw = ': heartbeat\r\n\r\n' + event({'choices': [{'delta': {'reasoning_content': 'Ignore me'}, 'index': 0}]})
        raw += 'data: {"choices":\r\ndata: [{"index":0,"delta":{"content":"译文 "}}]}\r\n\r\n'
        raw += event(chunk('completed')) + event(chunk(finish='stop'))
        raw += event({'choices': [], 'usage': {'total_tokens': 21}}) + 'data: [DONE]\r\n\r\n'
        result = self.provider(lambda *args: (200, raw.encode()), stream=True).generate(REQUEST)
        self.assertEqual(result.text, '译文 completed')
        self.assertEqual(result.usage['total_tokens'], 21)

    def test_disconnected_stream_is_not_accepted(self):
        calls = []
        def transport(*args):
            calls.append(1)
            return 200, event(chunk('partial')).encode()
        with patch('providers.openai_compatible.time.sleep'), self.assertRaises(ProviderResponseInterrupted):
            self.provider(transport, stream=True).generate(REQUEST)
        self.assertEqual(len(calls), 3)

    def test_reasoning_only_and_length_are_retriable_not_translations(self):
        for response in [ {'choices': [{'message': {'content': '', 'reasoning_content': 'Thinking'}, 'finish_reason': 'stop'}]},
                          {'choices': [{'message': {'content': 'partial'}, 'finish_reason': 'length'}]} ]:
            with self.subTest(response=response), patch('providers.openai_compatible.time.sleep'), self.assertRaises(ProviderResponseInterrupted):
                self.provider(lambda *args: (200, json.dumps(response).encode())).generate(REQUEST)

    def test_optional_field_fallback_and_exact_endpoint(self):
        seen = []
        def transport(url, headers, body, *_):
            payload=json.loads(body);seen.append((url,payload))
            if 'temperature' in payload:
                raise ProviderError('unsupported temperature', status=400)
            if payload.get('stream'):
                raise ProviderError('stream is not supported', status=400)
            return 200, json.dumps({'choices':[{'message':{'content':'done'}}]}).encode()
        p=OpenAICompatibleProvider(ProviderConfig('openai-compatible','https://gateway.example/v1/chat/completions',
            'KEY','model',stream=True),environ={'KEY':'test'},transport=transport)
        self.assertEqual(p.generate(REQUEST).text,'done')
        self.assertEqual(len(seen),3)
        self.assertTrue(all(url.endswith('/v1/chat/completions') for url,_ in seen))
        self.assertNotIn('temperature',seen[-1][1])
        self.assertFalse(seen[-1][1]['stream'])

    def test_quota_error_is_not_retried_and_credentials_are_redacted(self):
        seen=[]
        def transport(*args):
            seen.append(1)
            raise ProviderError('quota: synthetic-private-key',status=402)
        with self.assertRaisesRegex(ProviderError,'redacted') as error:
            self.provider(transport).generate(REQUEST)
        self.assertEqual(error.exception.status,402)
        self.assertEqual(len(seen),1)
        self.assertNotIn('synthetic-private-key',str(error.exception))

    def test_rate_limit_honors_bounded_retry_delay(self):
        calls=[]
        def transport(*args):
            calls.append(1)
            if len(calls)<3:raise ProviderTransientError('rate limit',status=429,retry_after=99)
            return 200,json.dumps({'choices':[{'message':{'content':'done'}}]}).encode()
        with patch('providers.openai_compatible.time.sleep') as sleep:
            self.assertEqual(self.provider(transport).generate(REQUEST).text,'done')
        self.assertEqual([c.args[0] for c in sleep.call_args_list],[60,60])

    def test_responses_and_anthropic_native_wire_formats(self):
        seen=[]
        def response_transport(url,headers,body,*_):
            seen.append((url,headers,json.loads(body)))
            return 200,event({'type':'response.output_text.delta','delta':'done'}).encode()+event({
                'type':'response.completed','response':{'status':'completed','output':[
                    {'type':'message','content':[{'type':'output_text','text':'done'}]}]}}).encode()
        self.assertEqual(self.provider(response_transport,api_mode='responses',stream=True).generate(REQUEST).text,'done')
        self.assertTrue(seen[-1][0].endswith('/responses'))
        self.assertFalse(seen[-1][2]['store'])
        raw=event({'type':'message_start','message':{'id':'id','usage':{'input_tokens':2}}})
        raw+=event({'type':'content_block_delta','delta':{'type':'text_delta','text':'done'}})
        raw+=event({'type':'message_delta','delta':{'stop_reason':'end_turn'},'usage':{'output_tokens':1}})
        raw+=event({'type':'message_stop'})
        def anthropic_transport(url,headers,body,*_):
            seen.append((url,headers,json.loads(body)));return 200,raw.encode()
        result=self.provider(anthropic_transport,api_mode='anthropic_messages',stream=True).generate(REQUEST)
        self.assertEqual(result.text,'done');self.assertEqual(result.usage['input_tokens'],2)
        self.assertTrue(seen[-1][0].endswith('/messages'));self.assertIn('x-api-key',seen[-1][1])
        self.assertNotIn('Authorization',seen[-1][1]);self.assertEqual(seen[-1][2]['max_tokens'],8192)

    def test_real_http_sse_with_small_network_chunks(self):
        body=(': keepalive\n\n'+event(chunk('结果'))+event(chunk(finish='stop'))+'data: [DONE]\n\n').encode()
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                assert payload['stream'] is True
                self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
                for pos in range(0,len(body),3):self.wfile.write(body[pos:pos+3]);self.wfile.flush()
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            p=OpenAICompatibleProvider(ProviderConfig('openai-compatible',f'http://127.0.0.1:{server.server_port}/v1',
                'KEY','model',stream=True),environ={'KEY':'test'})
            self.assertEqual(p.generate(REQUEST).text,'结果')
        finally:server.shutdown();server.server_close();thread.join()

    def test_timeout_adapts_remaining_batches_and_preserves_checkpoint(self):
        calls=[]
        class Provider:
            def generate(self,request):
                units=json.loads(request.user)['units'];calls.append([u['id'] for u in units])
                if len(units)>2:raise ProviderResponseInterrupted('idle timeout')
                return GenerationResponse(text=json.dumps({'units':[{'id':u['id'],'suggested_target':'Configure database '+u['id'],
                    'proposal_decision':'REPLACE','reason':'Instruction translated.'} for u in units]}),model='fake',provider='fake',response_id=None,usage={})
        units=[{'id':'U'+str(i),'source':'配置数据库','source_language':'zh-CN','target_language':'en',
                'location':str(i),'context':{'text_role':'PROSE'},'target':''} for i in range(12)]
        # Duplicated sources are locally de-duplicated: distinct prose makes all batches necessary.
        for i,u in enumerate(units):u['source']='配置数据库'+chr(0x4e00+i)
        with tempfile.TemporaryDirectory() as td:
            checkpoint=Path(td)/'checkpoint.json'
            result=translate_units(provider=Provider(),units=units,source_language='zh-CN',target_language='en',
                limits=TranslationLimits(max_units_per_batch=4),checkpoint_path=checkpoint)
            self.assertEqual(len(result['units']),12)
            self.assertEqual([len(ids) for ids in calls],[4,2,2,2,2,2,2])
            calls.clear()
            translate_units(provider=Provider(),units=units,source_language='zh-CN',target_language='en',
                limits=TranslationLimits(max_units_per_batch=4),checkpoint_path=checkpoint)
            self.assertEqual(calls,[])

if __name__=='__main__':unittest.main()

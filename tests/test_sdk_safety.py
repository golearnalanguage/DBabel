import gzip
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from providers import sdk_transport
from providers.base import ProviderError
from providers.openai_compatible import OpenAICompatibleProvider
from runtime.models import ProviderConfig, GenerationRequest


@unittest.skipUnless(sdk_transport.available('chat_completions'),'optional SDK not installed')
class SDKSafetyTests(unittest.TestCase):
    def exchange(self, handler, **kwargs):
        server=ThreadingHTTPServer(('127.0.0.1',0),handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            config=ProviderConfig('openai-compatible',f'http://127.0.0.1:{server.server_port}/v1','KEY','test',transport_backend='sdk',**kwargs)
            return OpenAICompatibleProvider(config,environ={'KEY':'fake-key'}).generate(GenerationRequest('Answer.','Test.'))
        finally:
            server.shutdown();server.server_close();thread.join()
    def test_extra_parameters_stay_json_and_request_id_redacts_bare_key(self):
        captured=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                captured.append((json.loads(self.rfile.read(int(self.headers['Content-Length']))),self.headers.get('X-Injected')))
                body=json.dumps({'choices':[{'message':{'content':'done'}}]}).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(body)))
                self.send_header('x-request-id','echo-fake-key');self.end_headers();self.wfile.write(body)
        result=self.exchange(Handler,extra_body={'timeout':None,'extra_headers':{'X-Injected':'wrong-layer'}})
        self.assertIn('timeout',captured[0][0]);self.assertIsNone(captured[0][1])
        self.assertNotIn('fake-key',json.dumps(result.diagnostics))
    def test_error_bodies_without_length_and_compressed_replies_are_bounded(self):
        for compressed in (False,True):
            with self.subTest(compressed=compressed):
                class Handler(BaseHTTPRequestHandler):
                    def log_message(self,*args): pass
                    def do_POST(self):
                        self.rfile.read(int(self.headers['Content-Length']))
                        body=b'x'*8192
                        if compressed: body=gzip.compress(body)
                        self.send_response(400)
                        if compressed:self.send_header('Content-Encoding','gzip')
                        self.end_headers();self.wfile.write(body)
                with self.assertRaisesRegex(ProviderError,'size limit|compressed content'):
                    self.exchange(Handler,max_response_bytes=1024)

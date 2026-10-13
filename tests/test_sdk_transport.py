"""Actual official SDKs against a synthetic local gateway, never paid APIs."""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from providers import sdk_transport
from providers.openai_compatible import OpenAICompatibleProvider
from runtime.models import ProviderConfig, GenerationRequest


@unittest.skipUnless(sdk_transport.available("chat_completions") and sdk_transport.available("anthropic_messages"),
                     "optional SDK integrations not installed")
class SDKTransportTests(unittest.TestCase):
    def test_three_protocols_and_single_retry_owner(self):
        calls = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                calls.append((self.path, payload))
                if payload["model"] == "retry-model" and sum(p["model"] == "retry-model" for _, p in calls) < 3:
                    body = json.dumps({"error": {"message": "rate limited"}}).encode()
                    self.send_response(429)
                else:
                    if self.path.endswith("/responses"):
                        response = {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "done"}]}]}
                    elif self.path.endswith("/messages"):
                        response = {"content": [{"type": "text", "text": "done"}], "stop_reason": "end_turn"}
                    else:
                        response = {"choices": [{"message": {"content": "done"}, "finish_reason": "stop"}]}
                    body = json.dumps(response).encode()
                    self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("x-request-id", "synthetic-request")
                self.end_headers()
                self.wfile.write(body)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for mode in ("chat_completions", "responses", "anthropic_messages"):
                config = ProviderConfig("openai-compatible", "http://127.0.0.1:{}/v1".format(server.server_port),
                    "KEY", "model", api_mode=mode, transport_backend="sdk")
                result = OpenAICompatibleProvider(config, environ={"KEY": "fake"}).generate(GenerationRequest("Answer.", "Test."))
                self.assertEqual(result.text, "done")
                self.assertEqual(result.diagnostics["request_id"], "synthetic-request")
            config = ProviderConfig("openai-compatible", "http://127.0.0.1:{}/v1".format(server.server_port),
                "KEY", "retry-model", transport_backend="sdk")
            with patch("providers.openai_compatible.time.sleep"):
                result = OpenAICompatibleProvider(config, environ={"KEY": "fake"}).generate(GenerationRequest("Answer.", "Test."))
            self.assertEqual(result.diagnostics["attempts"], 3)
            self.assertEqual(sum(p["model"] == "retry-model" for _, p in calls), 3)
            self.assertEqual([path for path, _ in calls[:3]], ["/v1/chat/completions", "/v1/responses", "/v1/messages"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

"""Actual official SDKs against a synthetic local gateway, never paid APIs."""
import json
import socket
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from providers import sdk_transport
from providers.base import ProviderTransientError
from providers.openai_compatible import OpenAICompatibleProvider
from runtime.models import ProviderConfig, GenerationRequest


@unittest.skipUnless(sdk_transport.available("chat_completions") and sdk_transport.available("anthropic_messages"),
                     "optional SDK integrations not installed")
class SDKTransportTests(unittest.TestCase):
    def test_system_proxy_exceptions_route_real_sdk_requests_directly(self):
        gateway_calls, proxy_calls = [], []

        class Gateway(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                gateway_calls.append((self.path, payload))
                if self.path.endswith("/responses"):
                    response = {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "direct"}]}]}
                elif self.path.endswith("/messages"):
                    response = {"content": [{"type": "text", "text": "direct"}], "stop_reason": "end_turn"}
                else:
                    response = {"choices": [{"message": {"content": "direct"}, "finish_reason": "stop"}]}
                body = json.dumps(response).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        class Proxy(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                proxy_calls.append(self.path)
                self.send_response(503)
                self.send_header("Content-Length", "0")
                self.end_headers()

        servers = [ThreadingHTTPServer(("127.0.0.1", 0), handler)
                   for handler in (Gateway, Proxy)]
        threads = [threading.Thread(target=server.serve_forever, daemon=True)
                   for server in servers]
        for thread in threads: thread.start()
        gateway, proxy = servers
        target = "gateway.example:{}".format(gateway.server_port)
        original_getaddrinfo = socket.getaddrinfo

        def local_dns(host, *args, **kwargs):
            # Keep even a routing regression confined to these local servers.
            if host == "gateway.example": host = "127.0.0.1"
            if host not in {"127.0.0.1", "::1"}:
                raise AssertionError("test attempted nonlocal network access")
            return original_getaddrinfo(host, *args, **kwargs)

        try:
            with patch("httpx2._utils.getproxies", return_value={
                    "http": "http://127.0.0.1:{}".format(proxy.server_port)}), \
                    patch("socket.getaddrinfo", side_effect=local_dns), \
                    patch("providers.openai_compatible.time.sleep"):
                # The same exception resolution is shared by all SDK protocols.
                for mode in ("chat_completions", "responses", "anthropic_messages"):
                    with self.subTest(mode=mode), patch("providers.sdk_transport.proxy_bypass", return_value=True) as bypass:
                        config = ProviderConfig("openai-compatible", "http://" + target + "/v1",
                            "KEY", "model", api_mode=mode, transport_backend="sdk", allow_insecure_http=True)
                        response = OpenAICompatibleProvider(config, environ={"KEY": "fake"}).generate(GenerationRequest("Answer.", "Test."))
                        self.assertEqual(response.text, "direct")
                        self.assertEqual(response.diagnostics["route"], "DIRECT_SYSTEM_BYPASS")
                        bypass.assert_called_once_with(target)
                        self.assertEqual(proxy_calls, [])

                for proxy_mode, exception, direct in (("system", False, False),
                        ("none", True, True), ("custom", True, False)):
                    with self.subTest(proxy_mode=proxy_mode), patch("providers.sdk_transport.proxy_bypass", return_value=exception) as bypass:
                        gateway_before, proxy_before = len(gateway_calls), len(proxy_calls)
                        config = ProviderConfig("openai-compatible", "http://" + target + "/v1",
                            "KEY", "model", transport_backend="sdk", allow_insecure_http=True,
                            proxy_mode=proxy_mode)
                        provider = OpenAICompatibleProvider(config, environ={"KEY": "fake"})
                        if direct:
                            response = provider.generate(GenerationRequest("Answer.", "Test."))
                            self.assertEqual(response.diagnostics["route"], "DIRECT_CONFIGURED")
                            self.assertEqual(len(gateway_calls) - gateway_before, 1)
                            self.assertEqual(len(proxy_calls), proxy_before)
                        else:
                            with self.assertRaises(ProviderTransientError) as failure:
                                provider.generate(GenerationRequest("Answer.", "Test."))
                            self.assertEqual(failure.exception.status, 503)
                            self.assertEqual(len(proxy_calls) - proxy_before, 3)
                            self.assertEqual(len(gateway_calls), gateway_before)
                        if proxy_mode == "system": bypass.assert_called_with(target)
                        else: bypass.assert_not_called()
        finally:
            for server in servers:
                server.shutdown()
                server.server_close()
            for thread in threads: thread.join()

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

import json
import tempfile
import threading
import unittest
from http.client import IncompleteRead
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.request import ProxyHandler

from providers.base import ProviderError, ProviderResponseInterrupted
from providers import openai_compatible
from providers.openai_compatible import (
    OpenAICompatibleProvider,
)
from runtime.models import (
    GenerationRequest,
    ProviderConfig,
)


class ProviderConfigTests(unittest.TestCase):
    def test_remote_plain_http_is_rejected(self):
        config = ProviderConfig(
            "openai-compatible",
            "http://example.com/v1",
            "KEY",
            "model-a",
        )

        with self.assertRaises(ValueError):
            config.validate()

    def test_local_plain_http_is_allowed(self):
        config = ProviderConfig(
            "openai-compatible",
            "http://127.0.0.1:8000/v1",
            "KEY",
            "model-a",
        )

        config.validate()

    def test_trusted_remote_http_requires_explicit_opt_in(self):
        config = ProviderConfig(
            "openai-compatible", "http://internal.example/v1", "KEY", "model-a",
            allow_insecure_http=True, proxy_mode="none",
        )
        config.validate()
        self.assertTrue(config.redacted()["allow_insecure_http"])

    def test_invalid_proxy_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            ProviderConfig("openai-compatible", "https://example.com/v1",
                           "KEY", "model-a", proxy_mode="bogus").validate()

    def test_unknown_config_keys_fail_closed(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "provider.json"

            path.write_text(
                json.dumps({
                    "provider":
                        "openai-compatible",
                    "base_url":
                        "https://example.com/v1",
                    "api_key_env":
                        "KEY",
                    "model":
                        "model-a",
                    "unexpected":
                        True,
                }),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                ProviderConfig.from_path(path)

    def test_missing_key_is_rejected(self):
        config = ProviderConfig(
            "openai-compatible",
            "https://example.com/v1",
            "DBABEL_TEST_KEY",
            "model-a",
        )

        with self.assertRaises(ValueError):
            config.resolve_api_key({})


class TransportPolicyTests(unittest.TestCase):
    def test_direct_remote_transport_disables_proxy(self):
        with patch.object(openai_compatible, "build_opener") as builder:
            openai_compatible._build_transport_opener(
                "https://internal.example/v1/chat/completions", "none"
            )
        self.assertTrue(any(isinstance(handler, ProxyHandler)
                            and handler.proxies == {}
                            for handler in builder.call_args.args))
    def test_localhost_transport_disables_proxy(
        self,
    ):
        with patch.object(
            openai_compatible,
            "build_opener",
        ) as builder:
            openai_compatible._build_transport_opener(
                "http://127.0.0.1:8000/v1/chat/completions"
            )

        handlers = (
            builder.call_args.args
        )

        proxy_handlers = [
            value
            for value in handlers
            if isinstance(
                value,
                ProxyHandler,
            )
        ]

        self.assertEqual(
            len(proxy_handlers),
            1,
        )

        self.assertEqual(
            proxy_handlers[0].proxies,
            {},
        )

        self.assertTrue(
            any(
                value
                is openai_compatible._NoRedirect
                for value in handlers
            )
        )

    def test_localhost_name_transport_disables_proxy(
        self,
    ):
        with patch.object(
            openai_compatible,
            "build_opener",
        ) as builder:
            openai_compatible._build_transport_opener(
                "http://localhost:11434/v1/chat/completions"
            )

        handlers = (
            builder.call_args.args
        )

        self.assertTrue(
            any(
                isinstance(
                    value,
                    ProxyHandler,
                )
                and value.proxies == {}
                for value in handlers
            )
        )

    def test_remote_transport_keeps_default_proxy_policy(
        self,
    ):
        with patch.object(
            openai_compatible,
            "build_opener",
        ) as builder:
            openai_compatible._build_transport_opener(
                "https://api.example.com/v1/chat/completions"
            )

        handlers = (
            builder.call_args.args
        )

        self.assertFalse(
            any(
                isinstance(
                    value,
                    ProxyHandler,
                )
                for value in handlers
            )
        )

        self.assertTrue(
            any(
                value
                is openai_compatible._NoRedirect
                for value in handlers
            )
        )


class ProviderTests(unittest.TestCase):
    def config(self):
        return ProviderConfig(
            "openai-compatible",
            "https://example.com/v1",
            "DBABEL_TEST_KEY",
            "model-a",
        )

    def test_request_contract_and_response_parse(
        self,
    ):
        observed = {}

        def transport(
            url,
            headers,
            body,
            timeout,
            max_bytes,
        ):
            observed.update(
                url=url,
                headers=dict(headers),
                body=json.loads(
                    body.decode("utf-8")
                ),
                timeout=timeout,
                max_bytes=max_bytes,
            )

            return 200, json.dumps({
                "id": "resp-1",
                "model": "model-a",
                "choices": [{
                    "message": {
                        "content": "translated"
                    }
                }],
                "usage": {
                    "total_tokens": 12
                },
            }).encode("utf-8")

        provider = OpenAICompatibleProvider(
            self.config(),
            {
                "DBABEL_TEST_KEY":
                    "top-secret"
            },
            transport,
        )

        result = provider.generate(
            GenerationRequest(
                system="system",
                user="user",
            )
        )

        self.assertEqual(
            result.text,
            "translated",
        )

        self.assertEqual(
            observed["url"],
            (
                "https://example.com/v1/"
                "chat/completions"
            ),
        )

        self.assertEqual(
            observed["headers"]
            ["Authorization"],
            "Bearer top-secret",
        )

        self.assertFalse(
            observed["body"]["stream"]
        )

    def test_reasoning_model_omits_temperature_for_new_api(self):
        observed = {}

        def transport(url, headers, body, timeout, max_bytes):
            observed.update(json.loads(body.decode("utf-8")))
            return 200, b'{"choices":[{"message":{"content":"OK"}}]}'

        config = ProviderConfig(
            "openai-compatible",
            "https://new-api.example.com/v1",
            "NEW_API_KEY",
            "gpt-6-astra",
        )
        provider = OpenAICompatibleProvider(
            config, {"NEW_API_KEY": "test-key"}, transport
        )
        self.assertEqual(
            provider.generate(GenerationRequest(system="S", user="U")).text,
            "OK",
        )
        self.assertNotIn("temperature", observed)
        self.assertEqual(observed["messages"][0]["role"], "system")

    def test_structured_text_parts_are_assembled(self):
        provider = OpenAICompatibleProvider(
            self.config(), {"DBABEL_TEST_KEY": "test-key"},
            lambda *args: (200, b'{"choices":[{"message":{"content":['
                           b'{"type":"text","text":"Hello "},'
                           b'{"type":"text","text":"world"}]}}]}'),
        )
        self.assertEqual(provider.generate(GenerationRequest("S", "U")).text,
                         "Hello world")

    def test_reasoning_only_completion_retries_then_splits(self):
        attempts = []
        def transport(*args):
            attempts.append(1)
            return 200, (b'{"choices":[{"finish_reason":"length",'
                         b'"message":{"content":"","reasoning_content":"thinking"}}]}')
        provider = OpenAICompatibleProvider(
            self.config(), {"DBABEL_TEST_KEY": "test-key"}, transport,
        )
        with patch.object(openai_compatible.time, "sleep"):
            with self.assertRaises(ProviderResponseInterrupted):
                provider.generate(GenerationRequest("S", "U"))
        self.assertEqual(len(attempts), 3)

    def test_deepseek_official_base_url_uses_chat_route(self):
        observed = {}

        def transport(url, headers, body, timeout, max_bytes):
            observed["url"] = url
            observed["authorization"] = headers["Authorization"]
            observed["body"] = json.loads(body.decode("utf-8"))
            return 200, b'{"choices":[{"message":{"content":"OK"}}]}'

        provider = OpenAICompatibleProvider(
            ProviderConfig("openai-compatible", "https://api.deepseek.com",
                           "DEEPSEEK_API_KEY", "deepseek-flash"),
            {"DEEPSEEK_API_KEY": "test-deepseek-key"}, transport,
        )
        self.assertEqual(provider.generate(
            GenerationRequest(system="S", user="U")
        ).text, "OK")
        self.assertEqual(observed["url"], "https://api.deepseek.com/chat/completions")
        self.assertEqual(observed["authorization"], "Bearer test-deepseek-key")
        self.assertEqual(observed["body"]["model"], "deepseek-flash")

    def test_malformed_response_fails_closed(
        self,
    ):
        provider = OpenAICompatibleProvider(
            self.config(),
            {
                "DBABEL_TEST_KEY":
                    "top-secret"
            },
            lambda *args: (
                200,
                b'{"choices":[]}',
            ),
        )

        with self.assertRaises(
            ProviderError
        ):
            provider.generate(
                GenerationRequest(
                    system="system",
                    user="user",
                )
            )

    def test_response_size_limit_is_enforced(
        self,
    ):
        config = ProviderConfig(
            "openai-compatible",
            "https://example.com/v1",
            "DBABEL_TEST_KEY",
            "model-a",
            max_response_bytes=1024,
        )

        provider = OpenAICompatibleProvider(
            config,
            {
                "DBABEL_TEST_KEY":
                    "top-secret"
            },
            lambda *args: (
                200,
                b"x" * 1025,
            ),
        )

        with self.assertRaises(
            ProviderError
        ):
            provider.generate(
                GenerationRequest(
                    system="system",
                    user="user",
                )
            )

    def test_incomplete_read_is_retried_with_same_request(self):
        bodies = []

        def transport(url, headers, body, timeout, max_bytes):
            bodies.append(body)
            if len(bodies) < 3:
                raise IncompleteRead(b"partial", 5)
            return 200, b'{"choices":[{"message":{"content":"OK"}}]}'

        provider = OpenAICompatibleProvider(
            self.config(), {"DBABEL_TEST_KEY": "test-key"}, transport)
        with patch.object(openai_compatible.time, "sleep") as sleep:
            result = provider.generate(GenerationRequest(system="S", user="U"))
        self.assertEqual(result.text, "OK")
        self.assertEqual(len(bodies), 3)
        self.assertEqual(bodies[0], bodies[1])
        self.assertEqual(sleep.call_count, 2)

    def test_short_http_body_is_retried_before_json_parse(self):
        calls = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                length = int(self.headers["Content-Length"])
                self.rfile.read(length)
                calls.append(self.path)
                body = (b'{' if len(calls) == 1 else
                        b'{"choices":[{"message":{"content":"OK"}}]}')
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body) + (20 if len(calls) == 1 else 0)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(body)
                self.close_connection = True

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            provider = OpenAICompatibleProvider(
                ProviderConfig("openai-compatible", f"http://127.0.0.1:{server.server_port}/v1",
                               "DBABEL_TEST_KEY", "model-a"),
                {"DBABEL_TEST_KEY": "test-key"})
            with patch.object(openai_compatible.time, "sleep"):
                result = provider.generate(GenerationRequest(system="S", user="U"))
            self.assertEqual(result.text, "OK")
            self.assertEqual(calls, ["/v1/chat/completions"] * 2)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()

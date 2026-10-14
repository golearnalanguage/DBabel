"""Failures retain actionable, bounded diagnostics across provider and CLI layers."""
import errno
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from urllib.error import URLError

from providers import sdk_transport
from providers.base import ProviderError, ProviderResponseInterrupted, ProviderTransientError
from providers.errors import provider_error_report, safe_text, service_request_id
from providers.openai_compatible import OpenAICompatibleProvider
from runtime.models import GenerationRequest, ProviderConfig

ROOT = Path(__file__).resolve().parents[1]
FIELDS = {"type", "title_zh", "title_en", "explanation_zh", "explanation_en", "actions_zh", "actions_en",
          "http_status", "service_message", "request_id", "attempts", "backend", "route"}


class ErrorGateway(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_POST(self):
        self.server.payloads.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        self.server.calls += 1
        status, message = (self.server.responses.pop(0) if self.server.responses
                           else (self.server.status, "synthetic service rejected fake-key"))
        if status == 200:
            body = json.dumps({"choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}]}).encode()
        else:
            body = json.dumps({"error": {"message": message}}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if self.server.request_id_header:
            self.send_header("x-request-id", "request-fake-key")
        self.end_headers()
        self.wfile.write(body)


class ProviderErrorTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), ErrorGateway)
        self.server.status, self.server.calls = 401, 0
        self.server.responses, self.server.payloads = [], []
        self.server.request_id_header = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = self.root / "provider.json"
        self.config.write_text(json.dumps({"provider": "openai-compatible",
            "base_url": "http://127.0.0.1:{}/v1".format(self.server.server_port),
            "api_key_env": "ERROR_TEST_KEY", "model": "synthetic-model", "transport_backend": "stdlib"}))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def assert_report(self, report):
        self.assertEqual(set(report), FIELDS)
        for key in ("title_zh", "title_en", "explanation_zh", "explanation_en", "actions_zh", "actions_en"):
            self.assertTrue(report[key], key)
        self.assertNotIn("fake-key", json.dumps(report, ensure_ascii=False))

    def test_real_http_errors_stop_401_and_retry_503_for_both_clients(self):
        for backend in ("stdlib", "sdk"):
            if backend == "sdk" and not sdk_transport.available("chat_completions"): continue
            for status, kind, attempts in ((401, "AUTHENTICATION_FAILED", 1), (503, "SERVICE_UNAVAILABLE", 3),
                                          (500, "SERVICE_FAILED", 3)):
                with self.subTest(backend=backend, status=status):
                    self.server.status, self.server.calls = status, 0
                    config = ProviderConfig("openai-compatible", "http://127.0.0.1:{}/v1".format(self.server.server_port),
                        "KEY", "synthetic-model", transport_backend=backend)
                    with patch("providers.openai_compatible.time.sleep"), self.assertRaises(ProviderError) as raised:
                        OpenAICompatibleProvider(config, environ={"KEY": "fake-key"}).generate(GenerationRequest("Answer.", "Test."))
                    report = provider_error_report(raised.exception)
                    self.assert_report(report)
                    self.assertEqual(report["type"], kind)
                    self.assertEqual(report["http_status"], status)
                    self.assertEqual(report["attempts"], attempts)
                    self.assertEqual(self.server.calls, attempts)
                    self.assertEqual(report["backend"], backend)
                    self.assertEqual(report["route"], "DIRECT_LOCAL")
                    self.assertEqual(report["request_id"], "request-[redacted]")
                    self.assertIn("synthetic service rejected", report["service_message"])
                    self.assertNotIn("fake-key", str(raised.exception))

    def test_probe_cli_failure_is_structured_and_stderr_is_safe(self):
        environment = dict(os.environ, ERROR_TEST_KEY="fake-key")
        command = [sys.executable, str(ROOT / "scripts/check_provider_connection.py"), "--provider-config", str(self.config)]
        for status, attempts in ((401, 1), (503, 3)):
            with self.subTest(status=status):
                self.server.status, self.server.calls = status, 0
                result = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 1)
                report = json.loads(result.stdout)
                self.assertEqual(report["status"], "FAILED")
                self.assert_report(report["error"])
                self.assertEqual(report["error"]["attempts"], attempts)
                self.assertIn("Connection test failed:", result.stderr)
                self.assertNotIn("fake-key", result.stdout + result.stderr)
        self.server.status = 200
        result = subprocess.run(command + ["--task-check"], env=environment, capture_output=True, text=True, timeout=15)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "CONTRACT_FAILED")
        self.assertTrue(report["connected"])
        self.assertFalse(report["contract_verified"])
        self.assertTrue(report["findings"])
        self.assertEqual(report["error"]["type"], "CONTRACT_FAILED")
        self.assert_report(report["error"])

    def test_optional_field_fallbacks_share_three_request_budget(self):
        for backend in ("stdlib", "sdk"):
            if backend == "sdk" and not sdk_transport.available("chat_completions"): continue
            with self.subTest(backend=backend):
                self.server.calls, self.server.payloads = 0, []
                self.server.responses = [(400, "unsupported temperature"), (400, "stream is not supported"),
                                         (503, "synthetic service unavailable")]
                config = ProviderConfig("openai-compatible", "http://127.0.0.1:{}/v1".format(self.server.server_port),
                    "KEY", "synthetic-model", transport_backend=backend, stream=True)
                with patch("providers.openai_compatible.time.sleep"), self.assertRaises(ProviderError) as raised:
                    OpenAICompatibleProvider(config, environ={"KEY": "fake-key"}).generate(GenerationRequest("Answer.", "Test."))
                report = provider_error_report(raised.exception)
                self.assertEqual(report["type"], "SERVICE_UNAVAILABLE")
                self.assertEqual(report["attempts"], 3)
                self.assertEqual(self.server.calls, 3)
                self.assertIn("temperature", self.server.payloads[0])
                self.assertNotIn("temperature", self.server.payloads[1])
                self.assertTrue(self.server.payloads[1]["stream"])
                self.assertFalse(self.server.payloads[2]["stream"])

    def test_error_message_request_id_is_retained_without_header(self):
        self.server.request_id_header = False
        for backend in ("stdlib", "sdk"):
            if backend == "sdk" and not sdk_transport.available("chat_completions"): continue
            with self.subTest(backend=backend):
                self.server.responses = [(401, "Invalid token (request id: synthetic-request-fake-key)")]
                config = ProviderConfig("openai-compatible", "http://127.0.0.1:{}/v1".format(self.server.server_port),
                    "KEY", "synthetic-model", transport_backend=backend)
                with self.assertRaises(ProviderError) as raised:
                    OpenAICompatibleProvider(config, environ={"KEY": "fake-key"}).generate(GenerationRequest("Answer.", "Test."))
                report = provider_error_report(raised.exception)
                self.assertEqual(report["request_id"], "synthetic-request-[redacted]")
                self.assert_report(report)

    def test_project_cli_and_saved_manifest_keep_same_provider_error(self):
        self.server.status = 503
        source = self.root / "manual.txt"
        source.write_text("请检查数据库配置并保存检查结果。\n", encoding="utf-8")
        command = [sys.executable, str(ROOT / "scripts/run_project.py"), str(source),
            "--source-language", "zh-CN", "--target-language", "en", "--text-role", "PROSE",
            "--provider-config", str(self.config), "--workspace-root", str(self.root / "runs")]
        result = subprocess.run(command, env=dict(os.environ, ERROR_TEST_KEY="fake-key"),
            capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 2, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "FAILED")
        self.assert_report(report["failure"]["provider_error"])
        self.assertEqual(report["failure"]["provider_error"]["attempts"], 3)
        saved = json.loads(next((self.root / "runs").glob("RUN_*/run.json")).read_text())
        self.assertEqual(saved["failure"]["provider_error"], report["failure"]["provider_error"])
        self.assertNotIn("fake-key", result.stdout + result.stderr + json.dumps(saved))


class CausalDiagnosticsTests(unittest.TestCase):
    def test_network_type_comes_from_original_exception_not_wrapper_text(self):
        for original, expected in ((socket.gaierror(-2, "name resolution failed"), "DNS_FAILED"),
                (ssl.SSLError("certificate verify failed"), "TLS_FAILED"),
                (ConnectionResetError(errno.ECONNRESET, "connection reset by peer"), "CONNECTION_RESET"),
                (TimeoutError("read timed out"), "TIMEOUT"),
                (ConnectionRefusedError(errno.ECONNREFUSED, "connection refused"), "CONNECTION_FAILED")):
            with self.subTest(expected=expected):
                transport = ProviderTransientError("provider network failed", details={"attempts": 3})
                transport.__cause__ = URLError(original)
                wrapper = RuntimeError("translation failed")
                wrapper.__cause__ = transport
                report = provider_error_report(wrapper)
                self.assertEqual(report["type"], expected)
                self.assertEqual(report["attempts"], 3)
                self.assertIn(str(original), report["service_message"])
        incomplete = provider_error_report(ProviderResponseInterrupted("output token limit reached"))
        self.assertEqual(incomplete["type"], "RESPONSE_INTERRUPTED")
        self.assertTrue(incomplete["actions_zh"])

    def test_every_text_field_redacts_credentials_and_bounds_details(self):
        error = ProviderError("fake-key", secrets=("fake-key",), details={"service_message": "fake-key " + "x" * 2000,
            "request_id": "fake-key", "backend": "fake-key", "route": "fake-key"})
        report = provider_error_report(error)
        self.assertNotIn("fake-key", json.dumps(report))
        self.assertLessEqual(len(report["service_message"]), 768)
        self.assertLessEqual(len(report["request_id"]), 128)
        value = safe_text("proxy http://user:private@proxy.example:8080 and https://service.example/?api_key=private&token=other")
        self.assertNotIn("private", value)
        self.assertNotIn("other", value)
        self.assertNotIn("user:", value)
        self.assertEqual(service_request_id({"requestId": "synthetic-id"}), "synthetic-id")
        self.assertEqual(service_request_id({"request_id": {"secret": "ignored"}}), None)
        self.assertEqual(service_request_id({"message": "request id: https://user:secret@host.example"}), None)
        self.assertEqual(service_request_id({"request_id": "body-id"}, {"x-request-id": "header-id"}), "header-id")

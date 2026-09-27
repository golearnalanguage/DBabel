import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


class NewAPIHandler(BaseHTTPRequestHandler):
    received = []

    def log_message(self, *args):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        self.received.append((self.path, self.headers.get("Authorization"), json.loads(body)))
        if self.headers.get("Authorization") != "Bearer test-new-api-token":
            self.send_error(401)
            return
        response = json.dumps({
            "model": "demo-model",
            "choices": [{"message": {"content": "OK"}}],
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)


class ProviderConnectionTests(unittest.TestCase):
    def test_new_api_token_and_chat_route_reach_provider(self):
        NewAPIHandler.received = []
        server = ThreadingHTTPServer(("127.0.0.1", 0), NewAPIHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                config = Path(tmp) / "provider.json"
                config.write_text(json.dumps({
                    "provider": "openai-compatible",
                    "base_url": "http://127.0.0.1:{}/v1".format(server.server_port),
                    "api_key_env": "NEW_API_KEY",
                    "model": "demo-model",
                }), encoding="utf-8")
                command = [sys.executable, str(REPO / "scripts/check_provider_connection.py"),
                           "--provider-config", str(config)]
                environment = os.environ.copy()
                environment["NEW_API_KEY"] = "test-new-api-token"
                success = subprocess.run(command, cwd=REPO, env=environment,
                                         capture_output=True, text=True, timeout=10)
                self.assertEqual(success.returncode, 0, success.stderr)
                self.assertEqual(json.loads(success.stdout)["status"], "CONNECTED")

                environment["NEW_API_KEY"] = "bad-token"
                failure = subprocess.run(command, cwd=REPO, env=environment,
                                         capture_output=True, text=True, timeout=10)
                self.assertEqual(failure.returncode, 1)
                self.assertIn("HTTP error: 401", failure.stderr)
                self.assertIn("gateway token was rejected", failure.stderr)
                self.assertNotIn("bad-token", failure.stderr)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(len(NewAPIHandler.received), 2)
        path, authorization, body = NewAPIHandler.received[0]
        self.assertEqual(path, "/v1/chat/completions")
        self.assertEqual(authorization, "Bearer test-new-api-token")
        self.assertEqual(body["model"], "demo-model")
        self.assertEqual([message["role"] for message in body["messages"]],
                         ["system", "user"])

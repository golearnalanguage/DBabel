#!/usr/bin/env python3
"""Start the local DBabel Review Workbench on 127.0.0.1 using Python stdlib only."""

from __future__ import annotations

import argparse
import json
import mimetypes
import secrets
import sys
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import unquote, urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
STATIC_ROOT = ROOT / "review_workbench" / "static"
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from export_reviewed_document import export_bundle
from review_model import (
    append_event,
    evaluate_export_gate,
    fresh_recheck_all,
    load_bundle,
    normalize_decision,
    progress,
    recheck_decision,
    save_decisions,
    utc_now,
)

MAX_BODY = 1024 * 1024


class WorkbenchState:
    def __init__(
        self,
        bundle: Path,
        repo_root: Path,
        token: str,
        original: Optional[Path] = None,
        output: Optional[Path] = None,
        glossary: Optional[Path] = None,
        receipt: Optional[Path] = None,
    ):
        self.bundle = bundle.resolve()
        self.repo_root = repo_root.resolve()
        self.token = token
        self.original = original.resolve() if original else None
        self.output = output.resolve() if output else None
        self.glossary = glossary.resolve() if glossary else None
        self.receipt = receipt.resolve() if receipt else (self.bundle / "export_receipt.json")
        self.lock = threading.RLock()
        self.origin = ""

    def data(self):
        return load_bundle(self.bundle)


class Handler(BaseHTTPRequestHandler):
    server_version = "DBabelReviewWorkbench/1.0"

    @property
    def state(self) -> WorkbenchState:
        return self.server.state  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args) -> None:
        # Avoid logging request paths/data. Only status-level output is useful here.
        sys.stderr.write("DBabel Workbench: " + (fmt % args).split('"')[0].strip() + "\n")

    def _security_headers(self) -> None:
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")

    def _json(self, status: int, value: Any) -> None:
        data = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._security_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _error(self, status: int, message: str) -> None:
        self._json(status, {"error": message})

    def _authorized_api(self) -> bool:
        if not self.path.startswith("/api/"):
            return True
        if self.headers.get("X-DBabel-Session") != self.state.token:
            self._error(HTTPStatus.FORBIDDEN, "invalid DBabel session token")
            return False
        origin = self.headers.get("Origin")
        if origin and origin != self.state.origin:
            self._error(HTTPStatus.FORBIDDEN, "origin rejected")
            return False
        return True

    def _body_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        if length < 0 or length > MAX_BODY:
            raise ValueError("request body too large")
        raw = self.rfile.read(length) if length else b"{}"
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("request body must be an object")
        return value

    def do_GET(self) -> None:
        if not self._authorized_api():
            return
        parsed = urlparse(self.path)
        if parsed.path == "/api/bootstrap":
            with self.state.lock:
                data = self.state.data()
                self._json(200, {
                    "session": data["session"],
                    "units": data["units"],
                    "issues": data["issues"],
                    "evidence": data["evidence"],
                    "decisions": data["decisions"],
                    "progress": progress(data),
                    "export_available": bool(self.state.original and self.state.output),
                })
            return
        if parsed.path == "/api/progress":
            with self.state.lock:
                self._json(200, progress(self.state.data()))
            return
        if parsed.path.startswith("/api/units/"):
            unit_id = unquote(parsed.path[len("/api/units/"):])
            with self.state.lock:
                data = self.state.data()
                unit = data["units_by_id"].get(unit_id)
                if not unit:
                    self._error(404, "unit not found")
                    return
                self._json(200, {
                    "unit": unit,
                    "decision": data["decisions_by_id"][unit_id],
                    "issues": [x for x in data["issues"] if x["unit_id"] == unit_id],
                })
            return
        self._serve_static(parsed.path)

    def do_PUT(self) -> None:
        if not self._authorized_api():
            return
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/decisions/"):
            self._error(404, "not found")
            return
        unit_id = unquote(parsed.path[len("/api/decisions/"):])
        try:
            incoming = self._body_json()
            with self.state.lock:
                data = self.state.data()
                unit = data["units_by_id"].get(unit_id)
                previous = data["decisions_by_id"].get(unit_id)
                if not unit or not previous:
                    self._error(404, "unit not found")
                    return
                saved = normalize_decision(unit, incoming, previous)
                recheck_issues = []
                if saved["status"] in {"ACCEPT_SUGGESTION", "KEEP_CURRENT", "USER_EDITED", "WAIVED"}:
                    saved, recheck_issues = recheck_decision(
                        self.state.repo_root, unit, saved, self.state.glossary
                    )
                decisions = [saved if x["unit_id"] == unit_id else x for x in data["decisions"]]
                save_decisions(self.state.bundle, decisions)
                event = {
                    "event": "DECISION_CHANGED",
                    "unit_id": unit_id,
                    "at": utc_now(),
                    "revision": saved["revision"],
                    "actor": "HUMAN",
                    "from_status": previous["status"],
                    "to_status": saved["status"],
                }
                append_event(self.state.bundle / "events.jsonl", event)
                if saved["status"] == "USER_EDITED":
                    append_event(self.state.bundle / "events.jsonl", {
                        "event": "TARGET_EDITED", "unit_id": unit_id, "at": utc_now(),
                        "revision": saved["revision"], "actor": "HUMAN"
                    })
                append_event(self.state.bundle / "events.jsonl", {
                    "event": "QA_RECHECKED", "unit_id": unit_id, "at": utc_now(),
                    "revision": saved["revision"], "actor": "SYSTEM",
                    "detail": saved["recheck"]["status"]
                })
                self._json(200, {"decision": saved, "recheck_issues": recheck_issues})
        except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
            self._error(400, str(exc))

    def do_POST(self) -> None:
        if not self._authorized_api():
            return
        parsed = urlparse(self.path)
        try:
            _ = self._body_json()
            if parsed.path == "/api/export-gate":
                with self.state.lock:
                    data = self.state.data()
                    updated, qa_by_unit = fresh_recheck_all(
                        data, self.state.repo_root, self.state.glossary
                    )
                    save_decisions(self.state.bundle, updated)
                    data = self.state.data()
                    gate = evaluate_export_gate(
                        data, fresh_qa_by_unit=qa_by_unit, original_path=self.state.original
                    )
                    self._json(200, gate)
                return
            if parsed.path == "/api/export":
                if not self.state.original or not self.state.output:
                    self._error(409, "start server with --original and --output to enable native export")
                    return
                with self.state.lock:
                    append_event(self.state.bundle / "events.jsonl", {
                        "event": "EXPORT_REQUESTED", "at": utc_now(), "revision": 0,
                        "actor": "HUMAN"
                    })
                    receipt = export_bundle(
                        self.state.bundle,
                        self.state.repo_root,
                        self.state.original,
                        self.state.output,
                        self.state.glossary,
                        self.state.receipt,
                    )
                    event_name = "EXPORT_COMPLETED" if receipt["status"] == "VERIFIED" else "EXPORT_BLOCKED"
                    append_event(self.state.bundle / "events.jsonl", {
                        "event": event_name, "at": utc_now(), "revision": 0,
                        "actor": "SYSTEM", "detail": receipt["status"]
                    })
                    if receipt["status"] == "VERIFIED":
                        append_event(self.state.bundle / "events.jsonl", {
                            "event": "ROUND_TRIP_VERIFIED", "at": utc_now(), "revision": 0,
                            "actor": "SYSTEM", "detail": receipt["output"]["sha256"]
                        })
                    self._json(200, receipt)
                return
            self._error(404, "not found")
        except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
            self._error(400, str(exc))

    def _serve_static(self, path: str) -> None:
        allowed = {
            "": "index.html",
            "/": "index.html",
            "/app.js": "app.js",
            "/style.css": "style.css",
            "/dbabel-workbench-logo.png": "dbabel-workbench-logo.png",
        }
        relative = allowed.get(path)
        if relative is None:
            self._error(404, "not found")
            return
        target = STATIC_ROOT / relative
        data = target.read_bytes()
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_response(200)
        self._security_headers()
        self.send_header("Content-Type", content_type + ("; charset=utf-8" if content_type.startswith("text/") or content_type == "application/javascript" else ""))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle")
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--original", help="Original DOCX for export; runtime-only and not written into bundle")
    parser.add_argument("--output", help="Reviewed output DOCX path")
    parser.add_argument("--glossary")
    parser.add_argument("--receipt")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    bundle = Path(args.bundle).resolve()
    load_bundle(bundle)  # fail before opening a port
    token = secrets.token_urlsafe(32)
    state = WorkbenchState(
        bundle,
        Path(args.repo_root),
        token,
        Path(args.original) if args.original else None,
        Path(args.output) if args.output else None,
        Path(args.glossary) if args.glossary else None,
        Path(args.receipt) if args.receipt else None,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.state = state  # type: ignore[attr-defined]
    host, port = server.server_address[:2]
    state.origin = "http://{}:{}".format(host, port)
    url = state.origin + "/#token=" + token
    print("DBabel Review Workbench")
    print("Listening on {} only".format(state.origin))
    print("Open: {}".format(url))
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

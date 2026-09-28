#!/usr/bin/env python3
"""Start the local DBabel Review Workbench on 127.0.0.1 using a local HTTP server."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import secrets
import sys
import threading
import tempfile
import uuid
import shutil
import zipfile
try:
    import fcntl
except ImportError:  # Windows has no fcntl; the macOS App uses this lock.
    fcntl = None
from xml.etree import ElementTree as ET
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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from review_exchange import upload_file, read_document, create_intake, glossary_score, render_result, RESULT_FORMATS
from glossary_io import load_glossary, validate_glossary
from export_reviewed_document import export_bundle
from build_post_review_report import build_report
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
    write_json,
    read_json,
)
from review_chat import append_message, chat_request, load_messages, prepare_attachments
from providers.openai_compatible import OpenAICompatibleProvider
from runtime.models import ProviderConfig

MAX_BODY = 48 * 1024 * 1024


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
        chat_provider: Optional[OpenAICompatibleProvider] = None,
    ):
        self.bundle = bundle.resolve()
        self.repo_root = repo_root.resolve()
        self.token = token
        self.original = original.resolve() if original else None
        self.output = output.resolve() if output else None
        self.glossary = glossary.resolve() if glossary else next((p for p in [self.bundle / "project-glossary.json", self.bundle / "project-glossary.csv"] if p.exists()), None)
        self.upload_root = self.bundle.parent / "dbabel-sessions"
        self.receipt = receipt.resolve() if receipt else (self.bundle / "export_receipt.json")
        self.chat_provider = chat_provider
        self.lock = threading.RLock()
        self.origin = ""
        self.configure_intake_export()

    def configure_intake_export(self):
        """Restore native export for a saved, aligned upload using its local copy."""
        if self.original or self.output:
            return
        intake = self.bundle / 'intake.json'
        if not intake.is_file():
            return
        info = json.loads(intake.read_text(encoding='utf-8'))
        layout_copy = info.get('layout_copy') is True
        target = info.get('source' if layout_copy else 'target') or {}
        fmt = target.get('format')
        if (layout_copy or info.get('alignment_confirmed')) and fmt in {'docx', 'txt', 'md', 'xlsx'}:
            original = self.bundle / 'inputs' / (('source.' if layout_copy else 'target.') + fmt)
            if original.is_file():
                self.original = original
                self.output = self.bundle / ('reviewed.' + fmt)
                self.receipt = Path(str(self.output) + '.receipt.json')

    def data(self):
        return load_bundle(self.bundle)

    def rejections(self):
        path = self.bundle / "rejected-translations.json"
        try:
            value = read_json(path)
        except (OSError, json.JSONDecodeError):
            try:
                value = read_json(self.bundle / "rejected-translations.backup.json")
            except (OSError, json.JSONDecodeError):
                if not path.exists():
                    return []
                raise
        if not isinstance(value, list):
            raise ValueError("rejected translations file must be an array")
        return value

    def remember_rejection(self, unit, reason):
        target = str(unit.get("suggested_target") or "")
        if not target.strip():
            return None
        key = "\0".join((str(unit.get("source_language") or ""),
                          str(unit.get("target_language") or ""),
                          str(unit.get("source") or ""), target))
        record_id = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
        record = {"id": record_id, "unit_id": unit["id"],
                  "source_language": unit.get("source_language", ""),
                  "target_language": unit.get("target_language", ""),
                  "source": unit.get("source", ""), "rejected_target": target,
                  "scope": ("TERM" if len(str(unit.get("source") or "").strip()) <= 32
                            and len(target.strip()) <= 100
                            and "\n" not in str(unit.get("source") or "")
                            and "\n" not in target else "SEGMENT"),
                  "reason": reason, "recorded_at": utc_now()}
        records = [item for item in self.rejections() if item.get("id") != record_id]
        records.append(record)
        write_json(self.bundle / "rejected-translations.json", records)
        write_json(self.bundle / "rejected-translations.backup.json", records)
        return record


def session_locked(method):
    """Keep token validation and dispatch on the same session during an intake switch."""
    def handle(self):
        with self.state.lock:
            return method(self)
    return handle


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

    @session_locked
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
                    "output_name": self.state.output.name if self.state.output else None,
                    "result_formats": sorted(RESULT_FORMATS),
                    "glossary_name": self.state.glossary.name if self.state.glossary else None,
                })
            return
        if parsed.path == "/api/rejection-memory":
            with self.state.lock:
                try:
                    self._json(200, {"records": self.state.rejections()})
                except (ValueError, OSError, json.JSONDecodeError) as exc:
                    self._error(400, str(exc))
            return
        if parsed.path == "/api/chat":
            with self.state.lock:
                self._json(200, {"available": self.state.chat_provider is not None,
                                 "messages": load_messages(self.state.bundle)})
            return
        if parsed.path == "/api/ui-state":
            with self.state.lock:
                try:
                    value = read_json(self.state.bundle / "ui_state.json")
                except (OSError, json.JSONDecodeError):
                    try:
                        value = read_json(self.state.bundle / "ui_state.backup.json")
                    except (OSError, json.JSONDecodeError):
                        value = {}
                self._json(200, value)
            return
        if parsed.path == "/api/post-review-report":
            with self.state.lock:
                self._json(200, build_report(self.state.data()))
            return
        if parsed.path == "/api/glossary":
            try:
                with self.state.lock:
                    self._json(200, glossary_score(self.state.data(), self.state.glossary) if self.state.glossary else {"entries": 0, "score": None, "checks": []})
            except (ValueError, OSError) as exc:
                self._error(400, str(exc))
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

    @session_locked
    def do_PUT(self) -> None:
        if not self._authorized_api():
            return
        parsed = urlparse(self.path)
        if parsed.path == "/api/ui-state":
            try:
                incoming = self._body_json()
                selected = incoming.get("selected")
                page = incoming.get("page", 0)
                page_size = incoming.get("page_size", 50)
                view = incoming.get("view", "Review")
                scroll_top = incoming.get("scroll_top", 0)
                drafts = incoming.get("drafts", {})
                if (selected is not None and not isinstance(selected, str)) or (
                    type(page) is not int or not 0 <= page <= 100000) or (
                    type(page_size) is not int or page_size not in {25, 50, 100, 200}) or (
                    view not in {"Review", "Terminology", "Rejection Memory", "Evidence", "Quality Check", "Reports", "Project Settings", "Activity"}) or (
                    type(scroll_top) not in {int, float} or not 0 <= scroll_top <= 10000000):
                    raise ValueError("invalid saved workspace position")
                with self.state.lock:
                    units_by_id = self.state.data()["units_by_id"]
                    if selected is not None and selected not in units_by_id:
                        raise ValueError("selected unit does not belong to this session")
                    if not isinstance(drafts, dict) or len(drafts) > len(units_by_id):
                        raise ValueError("invalid saved translation drafts")
                    for unit_id, draft in drafts.items():
                        if (unit_id not in units_by_id or not isinstance(draft, dict)
                                or set(draft) != {"target", "note", "editing"}
                                or not isinstance(draft["target"], str)
                                or len(draft["target"]) > 100000
                                or not isinstance(draft["note"], str)
                                or len(draft["note"]) > 10000
                                or type(draft["editing"]) is not bool):
                            raise ValueError("invalid saved translation draft")
                    value = {"selected": selected, "page": page, "page_size": page_size,
                             "view": view, "scroll_top": scroll_top, "drafts": drafts,
                             "updated_at": utc_now()}
                    write_json(self.state.bundle / "ui_state.json", value)
                    write_json(self.state.bundle / "ui_state.backup.json", value)
                    self._json(200, value)
            except (ValueError, OSError, json.JSONDecodeError) as exc:
                self._error(400, str(exc))
            return
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
                rejection_reason = incoming.get("rejection_reason", "")
                if not isinstance(rejection_reason, str) or (
                    rejection_reason and (saved["status"] != "BLOCKED"
                                          or len(rejection_reason.strip()) > 2000)
                ):
                    raise ValueError("invalid rejection reason")
                recheck_issues = []
                if saved["status"] in {"ACCEPT_SUGGESTION", "KEEP_CURRENT", "USER_EDITED", "WAIVED"}:
                    saved, recheck_issues = recheck_decision(
                        self.state.repo_root, unit, saved, self.state.glossary
                    )
                linked = []
                if saved["status"] in {"ACCEPT_SUGGESTION", "KEEP_CURRENT"}:
                    for candidate in data["units"]:
                        if candidate["id"] == unit_id:
                            continue
                        prior = data["decisions_by_id"][candidate["id"]]
                        if prior["status"] != "UNREVIEWED":
                            continue
                        if any(candidate.get(field) != unit.get(field) for field in (
                            "source", "current_target", "suggested_target",
                            "source_language", "target_language", "text_role", "labels"
                        )):
                            continue
                        proposed = normalize_decision(candidate, {"status": saved["status"]}, prior)
                        proposed, candidate_issues = recheck_decision(
                            self.state.repo_root, candidate, proposed, self.state.glossary
                        )
                        linked.append((candidate, prior, proposed, candidate_issues))
                replacements = {unit_id: saved}
                replacements.update({candidate["id"]: proposed for candidate, _, proposed, _ in linked})
                decisions = [replacements.get(x["unit_id"], x) for x in data["decisions"]]
                save_decisions(self.state.bundle, decisions)
                remembered = (self.state.remember_rejection(unit, rejection_reason.strip())
                              if saved["status"] == "BLOCKED" and rejection_reason.strip() else None)
                event = {
                    "event": "DECISION_CHANGED",
                    "unit_id": unit_id,
                    "at": utc_now(),
                    "revision": saved["revision"],
                    "actor": "HUMAN",
                    "from_status": previous["status"],
                    "to_status": saved["status"],
                    "before_target": previous.get("approved_target", unit.get("current_target", "")),
                    "after_target": saved.get("approved_target", unit.get("current_target", "")),
                    "location": unit.get("location"),
                }
                append_event(self.state.bundle / "events.jsonl", event)
                for candidate, prior, proposed, _ in linked:
                    append_event(self.state.bundle / "events.jsonl", {
                        "event": "DECISION_CHANGED", "unit_id": candidate["id"],
                        "at": utc_now(), "revision": proposed["revision"],
                        "actor": "HUMAN_LINKED", "linked_from": unit_id,
                        "from_status": prior["status"], "to_status": proposed["status"],
                        "before_target": prior.get("approved_target", candidate.get("current_target", "")),
                        "after_target": proposed.get("approved_target", candidate.get("current_target", "")),
                        "location": candidate.get("location"),
                    })
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
                self._json(200, {"decision": saved, "recheck_issues": recheck_issues,
                                 "rejection_memory": remembered,
                                 "linked_decisions": [{"decision": proposed, "recheck_issues": issues}
                                                      for _, _, proposed, issues in linked]})
        except (ValueError, RuntimeError, OSError, json.JSONDecodeError, zipfile.BadZipFile, ET.ParseError, KeyError, IndexError) as exc:
            self._error(400, str(exc))

    def do_POST(self) -> None:
        if urlparse(self.path).path == "/api/chat/provider":
            self._configure_chat_provider()
            return
        if urlparse(self.path).path == "/api/chat":
            self._post_chat()
            return
        self._post_locked()

    def _configure_chat_provider(self) -> None:
        if not self._authorized_api():
            return
        try:
            body = self._body_json()
            config_data = body.get("config")
            key = body.get("key")
            allowed = {"provider", "base_url", "api_key_env", "model",
                       "timeout_seconds", "max_response_bytes",
                       "allow_insecure_http", "proxy_mode"}
            required = {"provider", "base_url", "api_key_env", "model"}
            if (not isinstance(config_data, dict)
                    or not required <= set(config_data)
                    or not set(config_data) <= allowed
                    or not isinstance(key, str) or not 1 <= len(key) <= 4096):
                raise ValueError("invalid chat provider configuration")
            config = ProviderConfig(**config_data)
            provider = OpenAICompatibleProvider(config, {config.api_key_env: key})
            with self.state.lock:
                self.state.chat_provider = provider
            self._json(200, {"available": True})
        except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
            self._error(400, str(exc))

    def _post_chat(self) -> None:
        if not self._authorized_api():
            return
        try:
            body = self._body_json()
            with self.state.lock:
                provider = self.state.chat_provider
                if provider is None:
                    self._error(503, "Configure an API service in the App to use review chat.")
                    return
                bundle = self.state.bundle
                unit_id = body.get("unit_id")
                if unit_id is not None and not isinstance(unit_id, str):
                    raise ValueError("unit_id must be a string")
                message = body.get("message")
                if not isinstance(message, str) or not message.strip() or len(message) > 4000:
                    raise ValueError("message must contain 1–4000 characters")
                records, documents, images = prepare_attachments(bundle, body.get("attachments"))
                request = chat_request(self.state.data(), load_messages(bundle),
                                       unit_id, message, documents, images)
                user_message = append_message(bundle, "user", message.strip(),
                                              unit_id, records)
            try:
                response = provider.generate(request)
            except Exception as exc:
                self._error(502, "AI service request failed: {}".format(exc))
                return
            with self.state.lock:
                answer = append_message(bundle, "assistant", response.text[:20000], unit_id)
            self._json(200, {"question": user_message, "answer": answer})
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            self._error(400, str(exc))

    @session_locked
    def _post_locked(self) -> None:
        if not self._authorized_api():
            return
        parsed = urlparse(self.path)
        try:
            body = self._body_json()

            if parsed.path == "/api/rejection-memory/remove":
                record_id = body.get("id")
                if not isinstance(record_id, str) or not record_id:
                    raise ValueError("rejection record id is required")
                with self.state.lock:
                    records = self.state.rejections()
                    retained = [item for item in records if item.get("id") != record_id]
                    if len(retained) == len(records):
                        raise ValueError("rejection record not found")
                    write_json(self.state.bundle / "rejected-translations.json", retained)
                    write_json(self.state.bundle / "rejected-translations.backup.json", retained)
                    append_event(self.state.bundle / "events.jsonl", {
                        "event": "REJECTION_MEMORY_REMOVED", "at": utc_now(),
                        "actor": "HUMAN", "detail": record_id,
                    })
                    self._json(200, {"records": retained})
                return

            if parsed.path in {"/api/intake/inspect", "/api/intake/create"}:
                with self.state.lock, tempfile.TemporaryDirectory() as td:
                    source_dir = Path(td)/"source"; source_dir.mkdir()
                    source = upload_file(body.get("source"), source_dir)
                    if parsed.path.endswith("inspect"):
                        info = read_document(source)
                        info["segment_count"] = len(info.pop("segments"))
                        self._json(200, info)
                        return
                    target = None
                    if body.get("target"):
                        target_dir = Path(td)/"target"; target_dir.mkdir()
                        target = upload_file(body["target"], target_dir)
                    languages = body.get("target_languages")
                    if not isinstance(languages, list) or not all(isinstance(x, str) for x in languages):
                        raise ValueError("target_languages must be an array of language tags")
                    self.state.upload_root.mkdir(parents=True, exist_ok=True)
                    bundle = self.state.upload_root/(uuid.uuid4().hex+".dbreview")
                    try:
                        create_intake(source, bundle, str(body.get("source_language", "")), languages, target, body.get("alignment_confirmed") is True)
                    except Exception:
                        if bundle.exists(): shutil.rmtree(bundle)
                        raise
                    self.state.bundle = bundle
                    self.state.original = None
                    self.state.output = None
                    self.state.glossary = None
                    self.state.receipt = bundle/"export_receipt.json"
                    self.state.configure_intake_export()
                    self.state.token = secrets.token_urlsafe(32)
                    self._json(200, {"session_id": self.state.data()["session"]["session_id"], "bundle": str(bundle), "token": self.state.token})
                return
            if parsed.path == "/api/glossary":
                with self.state.lock, tempfile.TemporaryDirectory() as td:
                    path = upload_file(body.get("file"), td)
                    if path.suffix.lower() not in {".json", ".csv"}:
                        raise ValueError("Use the project glossary JSON or CSV template.")
                    score = glossary_score(self.state.data(), path)
                    dest = self.state.bundle/("project-glossary"+path.suffix.lower())
                    for old in self.state.bundle.glob("project-glossary.*"):
                        if old.suffix in {".json", ".csv"} and old != dest: old.unlink()
                    dest.write_bytes(path.read_bytes())
                    self.state.glossary = dest
                    self._json(200, score)
                return
            if parsed.path == "/api/results":
                with self.state.lock:
                    fmt = body.get("format", "json")
                    data = self.state.data()
                    content = render_result(data, fmt)
                    original = data["session"].get("original", {}).get("filename", "document")
                    stem = Path(str(original)).stem
                    safe_stem = "".join(c if c.isalnum() or c in " ._-" else "-" for c in stem)
                    safe_stem = safe_stem.strip(" .-")[:80] or "document"
                    self._json(200, {"filename": "Review - " + safe_stem + "." + fmt,
                                     "content": content, "content_type": RESULT_FORMATS[fmt]})
                return

            if parsed.path == "/api/decisions/bulk":
                status = str(
                    body.get("status") or ""
                )

                if status not in {
                    "ACCEPT_SUGGESTION",
                    "KEEP_CURRENT",
                    "DEFERRED",
                }:
                    raise ValueError(
                        "bulk decisions support "
                        "ACCEPT_SUGGESTION, KEEP_CURRENT or DEFERRED only"
                    )

                raw_ids = body.get("unit_ids")

                if (
                    not isinstance(raw_ids, list)
                    or not raw_ids
                ):
                    raise ValueError(
                        "bulk decision requires "
                        "non-empty unit_ids array"
                    )

                unit_ids = [
                    str(value)
                    for value in raw_ids
                ]

                if any(
                    not value
                    for value in unit_ids
                ):
                    raise ValueError(
                        "bulk unit_ids cannot contain "
                        "empty values"
                    )

                if len(unit_ids) != len(
                    set(unit_ids)
                ):
                    raise ValueError(
                        "bulk unit_ids contain duplicates"
                    )

                with self.state.lock:
                    data = self.state.data()

                    missing = [
                        unit_id
                        for unit_id in unit_ids
                        if unit_id
                        not in data["units_by_id"]
                    ]

                    if missing:
                        raise ValueError(
                            "bulk decision references "
                            "unknown unit(s): {}".format(
                                ", ".join(missing)
                            )
                        )

                    staged = dict(
                        data["decisions_by_id"]
                    )
                    changes = []

                    # Nothing is persisted until every
                    # requested unit has normalized and
                    # rechecked successfully.
                    for unit_id in unit_ids:
                        unit = data[
                            "units_by_id"
                        ][unit_id]

                        previous = data[
                            "decisions_by_id"
                        ][unit_id]

                        incoming = {
                            "status": status,
                            "reviewer_note": str(
                                previous.get(
                                    "reviewer_note"
                                )
                                or ""
                            ),
                        }

                        saved = normalize_decision(
                            unit,
                            incoming,
                            previous,
                        )

                        recheck_issues = []

                        if status in {"ACCEPT_SUGGESTION", "KEEP_CURRENT"}:
                            (
                                saved,
                                recheck_issues,
                            ) = recheck_decision(
                                self.state.repo_root,
                                unit,
                                saved,
                                self.state.glossary,
                            )

                        staged[unit_id] = saved

                        changes.append(
                            (
                                unit_id,
                                previous,
                                saved,
                                recheck_issues,
                            )
                        )

                    decisions = [
                        staged[
                            decision["unit_id"]
                        ]
                        for decision
                        in data["decisions"]
                    ]

                    save_decisions(
                        self.state.bundle,
                        decisions,
                    )

                    results = []

                    for (
                        unit_id,
                        previous,
                        saved,
                        recheck_issues,
                    ) in changes:
                        append_event(
                            self.state.bundle
                            / "events.jsonl",
                            {
                                "event":
                                    "DECISION_CHANGED",
                                "unit_id": unit_id,
                                "at": utc_now(),
                                "revision":
                                    saved["revision"],
                                "actor": "HUMAN",
                                "from_status":
                                    previous["status"],
                                "to_status":
                                    saved["status"],
                                "before_target": previous.get("approved_target", data["units_by_id"][unit_id].get("current_target", "")),
                                "after_target": saved.get("approved_target", data["units_by_id"][unit_id].get("current_target", "")),
                                "location": data["units_by_id"][unit_id].get("location"),
                            },
                        )

                        if status in {"KEEP_CURRENT", "ACCEPT_SUGGESTION"}:
                            append_event(
                                self.state.bundle
                                / "events.jsonl",
                                {
                                    "event":
                                        "QA_RECHECKED",
                                    "unit_id":
                                        unit_id,
                                    "at": utc_now(),
                                    "revision":
                                        saved["revision"],
                                    "actor": "SYSTEM",
                                    "detail":
                                        saved[
                                            "recheck"
                                        ]["status"],
                                },
                            )

                        results.append(
                            {
                                "decision": saved,
                                "recheck_issues":
                                    recheck_issues,
                            }
                        )

                    self._json(
                        200,
                        {
                            "results": results,
                        },
                    )

                return

            if parsed.path == "/api/export-gate":
                with self.state.lock:
                    data = self.state.data()
                    mode = body.get("export_mode", "DRAFT")
                    updated, qa_by_unit = None, None
                    if mode != "DRAFT":
                        updated, qa_by_unit = fresh_recheck_all(
                            data, self.state.repo_root, self.state.glossary
                        )
                        save_decisions(self.state.bundle, updated)
                        data = self.state.data()
                    gate = evaluate_export_gate(
                        data, fresh_qa_by_unit=qa_by_unit, original_path=self.state.original,
                        export_mode=mode
                    )
                    self._json(200, dict(gate, review_decisions=updated,
                        qa_issues=[issue for rows in (qa_by_unit or {}).values() for issue in rows]))
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
                    mode = body.get("export_mode", "DRAFT")
                    export_output = self.state.output
                    export_receipt = self.state.receipt
                    if mode in {"CHECKPOINT", "DRAFT"} or export_output.exists() or export_receipt.exists():
                        index = 1
                        while True:
                            candidate = self.state.output.with_name(self.state.output.stem + ".{}-{}".format(mode.lower(), index) + self.state.output.suffix)
                            if not candidate.exists() and not candidate.with_suffix('.receipt.json').exists():
                                export_output = candidate
                                export_receipt = candidate.with_suffix('.receipt.json')
                                break
                            index += 1
                    receipt = export_bundle(
                        self.state.bundle,
                        self.state.repo_root,
                        self.state.original,
                        export_output,
                        self.state.glossary,
                        export_receipt,
                        export_mode=mode,
                    )
                    succeeded = receipt["status"] in {"VERIFIED", "DRAFT_EXPORTED"}
                    event_name = "EXPORT_COMPLETED" if succeeded else "EXPORT_BLOCKED"
                    append_event(self.state.bundle / "events.jsonl", {
                        "event": event_name, "at": utc_now(), "revision": 0,
                        "actor": "SYSTEM", "detail": receipt["status"]
                    })
                    if succeeded:
                        append_event(self.state.bundle / "events.jsonl", {
                            "event": "ROUND_TRIP_VERIFIED", "at": utc_now(), "revision": 0,
                            "actor": "SYSTEM", "detail": receipt["output"]["sha256"]
                        })
                    response = dict(receipt)
                    if succeeded:
                        import base64
                        import io
                        archive = io.BytesIO()
                        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as package:
                            paths = [export_output, export_receipt] + [Path(a['path']) for a in receipt.get('artifacts', [])]
                            for path in paths:
                                package.writestr(path.name, path.read_bytes())
                        response['delivery_archive'] = {'filename': export_output.name + '.delivery.zip',
                            'content_base64': base64.b64encode(archive.getvalue()).decode('ascii')}
                    self._json(200, response)
                return
            self._error(404, "not found")
        except (ValueError, RuntimeError, OSError, json.JSONDecodeError, zipfile.BadZipFile, ET.ParseError, KeyError, IndexError) as exc:
            self._error(400, str(exc))

    def _serve_static(self, path: str) -> None:
        allowed = {
            "": "index.html",
            "/": "index.html",
            "/app.js": "app.js",
            "/i18n.js": "i18n.js",
            "/desktop_theme.js": "desktop_theme.js",
            "/exchange.js": "exchange.js",
            "/dbabel-logo-light.svg": "dbabel-logo-light.svg",
            "/dbabel-logo-dark.svg": "dbabel-logo-dark.svg",
            "/workbench_views.js": "workbench_views.js",
            "/style.css": "style.css",
            "/dbabel-workbench-logo.png": "dbabel-workbench-logo.png",
        }
        relative = allowed.get(path)
        if relative is None:
            self._error(404, "not found")
            return
        target = STATIC_ROOT / relative
        # One ordered runtime response prevents a partially loaded dependency set
        # after a quick reload. The source files stay separate for maintenance.
        if relative == "app.js":
            data = b"\n".join((STATIC_ROOT/name).read_bytes() for name in
                              ("i18n.js", "exchange.js", "workbench_views.js", "app.js"))
        else:
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
    parser.add_argument("--original", help="Original DOCX, TXT or MD for export")
    parser.add_argument("--port", type=int, default=0, help="Local port; 0 chooses an available port")
    parser.add_argument("--output", help="Reviewed output path with the original document extension")
    parser.add_argument("--glossary")
    parser.add_argument("--receipt")
    parser.add_argument("--provider-config", help="Optional OpenAI-compatible API for session chat")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    bundle = Path(args.bundle).resolve()
    load_bundle(bundle)  # fail before opening a port
    session_lock = (bundle / ".workbench.lock").open("a+")
    if fcntl is not None:
        try:
            fcntl.flock(session_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error("This review session is already open in another DBabel window.")
    token = secrets.token_urlsafe(32)
    state = WorkbenchState(
        bundle,
        Path(args.repo_root),
        token,
        Path(args.original) if args.original else None,
        Path(args.output) if args.output else None,
        Path(args.glossary) if args.glossary else None,
        Path(args.receipt) if args.receipt else None,
        OpenAICompatibleProvider(ProviderConfig.from_path(Path(args.provider_config)))
        if args.provider_config else None,
    )
    if not 0 <= args.port <= 65535:
        parser.error('Port must be between 0 and 65535')
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
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
        if fcntl is not None:
            fcntl.flock(session_lock.fileno(), fcntl.LOCK_UN)
        session_lock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

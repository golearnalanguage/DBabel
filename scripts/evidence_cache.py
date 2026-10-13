#!/usr/bin/env python3
"""Retain source-bound evidence and report stale dependencies without editing review decisions."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, Optional

from validate_report import validator

MAX_SOURCE_BYTES = 16 * 1024 * 1024
STATES = {"CURRENT", "STALE", "CONFLICTING", "INSUFFICIENT"}


def _bytes(path: Path) -> bytes:
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_SOURCE_BYTES + 1)
    if len(raw) > MAX_SOURCE_BYTES:
        raise ValueError("Evidence material exceeds the 16 MiB document intake limit")
    return raw


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _time(value: str) -> datetime:
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError) as exc:
        raise ValueError("Use an ISO-8601 timestamp with a timezone") from exc
    if stamp.tzinfo is None:
        raise ValueError("Evidence expiry requires an explicit timezone")
    return stamp.astimezone(timezone.utc)


def _new_private(path: Path, raw: bytes) -> bool:
    """Publish a complete private artifact exclusively; existing files remain untouched."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=".evidence-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
            return True
        except FileExistsError:
            return False
    finally:
        os.unlink(temporary)


def _semantic(record: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in record.items() if k not in {"cache_id", "recorded_at", "record_sha256"}}


def _validate_record(record: Any) -> Dict[str, Any]:
    required = {"format_version", "cache_id", "recorded_at", "record_sha256", "evidence",
                "scope", "source", "dependent_unit_ids", "expires_at"}
    if not isinstance(record, dict) or set(record) != required or record["format_version"] != "1.0":
        raise ValueError("Invalid evidence-cache record contract")
    if record["record_sha256"] != _hash(_canonical({k: v for k, v in record.items() if k != "record_sha256"})):
        raise ValueError("Evidence-cache record integrity mismatch")
    if record["cache_id"] != "ec_" + _hash(_canonical(_semantic(record))):
        raise ValueError("Evidence-cache semantic identity mismatch")
    if not isinstance(record["scope"], dict):
        raise ValueError("Evidence scope must be an object")
    if not isinstance(record["dependent_unit_ids"], list) or any(
            not isinstance(v, str) or not v.strip() for v in record["dependent_unit_ids"]):
        raise ValueError("Evidence dependencies must be nonempty unit IDs")
    if record["expires_at"] is not None:
        _time(record["expires_at"])
    _time(record["recorded_at"])
    source = record["source"]
    if not isinstance(source, dict) or set(source) != {"path", "sha256", "snapshot"}:
        raise ValueError("Invalid evidence source identity")
    if (not isinstance(source["path"], str) or not Path(source["path"]).is_absolute()
            or not isinstance(source["sha256"], str) or len(source["sha256"]) != 64
            or any(c not in "0123456789abcdef" for c in source["sha256"])
            or source["snapshot"] != "sources/" + source["sha256"]):
        raise ValueError("Invalid evidence source path or snapshot identity")
    errors = list(validator("evidence.schema.json").iter_errors(record["evidence"]))
    if errors:
        raise ValueError("Invalid evidence record: " + errors[0].message)
    return record


def record_evidence(cache: Path, evidence: Dict[str, Any], source: Path,
                    scope: Dict[str, Any], dependent_unit_ids: Optional[list[str]] = None,
                    expires_at: Optional[str] = None) -> Dict[str, Any]:
    """Snapshot caller-supplied source bytes and evidence; no remote fetch or verdict upgrade."""
    if not isinstance(scope, dict):
        raise ValueError("Evidence scope must be a JSON object")
    source = Path(source).resolve()
    raw = _bytes(source)
    digest = _hash(raw)
    record = {"format_version": "1.0", "evidence": evidence, "scope": scope,
              "source": {"path": str(source), "sha256": digest, "snapshot": "sources/" + digest},
              "dependent_unit_ids": sorted(set(dependent_unit_ids or [])), "expires_at": expires_at}
    record["cache_id"] = "ec_" + _hash(_canonical(record))
    record["recorded_at"] = datetime.now(timezone.utc).isoformat()
    record["record_sha256"] = _hash(_canonical(record))
    _validate_record(record)
    if len(_canonical(record)) > MAX_SOURCE_BYTES:
        raise ValueError("Evidence-cache record exceeds the 16 MiB document intake limit")
    cache = Path(cache)
    snapshot = cache / record["source"]["snapshot"]
    if not _new_private(snapshot, raw) and _hash(_bytes(snapshot)) != digest:
        raise ValueError("Existing cached source content does not match its digest")
    destination = cache / "records" / (record["cache_id"] + ".json")
    if not _new_private(destination, _canonical(record) + b"\n"):
        existing = _validate_record(json.loads(_bytes(destination)))
        if _semantic(existing) != _semantic(record):
            raise ValueError("Conflicting evidence-cache record")
        return existing
    return record


def check_cache(cache: Path, scope: Optional[Dict[str, Any]] = None,
                session: Optional[Path] = None, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Return current local validity and affected units; all review data remain read-only."""
    if scope is not None and not isinstance(scope, dict):
        raise ValueError("Current scope must be a JSON object")
    if not (Path(cache) / "records").is_dir():
        raise ValueError("Evidence cache has no records directory")
    unit_dependencies: Dict[str, list[str]] = {}
    if session is not None:
        units_path = Path(session) / "units.jsonl"
        raw = _bytes(units_path)
        for line in raw.decode("utf-8").splitlines():
            if not line.strip():
                continue
            unit = json.loads(line)
            if (not isinstance(unit, dict) or not isinstance(unit.get("id"), str)
                    or not isinstance(unit.get("evidence_refs", []), list)
                    or any(not isinstance(ref, str) for ref in unit.get("evidence_refs", []))):
                raise ValueError("Session units require IDs and evidence-reference lists")
            for ref in unit.get("evidence_refs", []):
                unit_dependencies.setdefault(ref, []).append(unit["id"])
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Cache check time requires a timezone")
    results = []
    for path in sorted((Path(cache) / "records").glob("*.json")):
        record = _validate_record(json.loads(_bytes(path)))
        if path.stem != record["cache_id"]:
            raise ValueError("Evidence cache filename does not match record identity")
        source = record["source"]
        # The validated snapshot path has no caller-controlled traversal segments.
        if _hash(_bytes(Path(cache) / source["snapshot"])) != source["sha256"]:
            raise ValueError("Cached source snapshot integrity mismatch")
        reasons = []
        try:
            if _hash(_bytes(Path(source["path"]))) != source["sha256"]:
                reasons.append("SOURCE_CHANGED")
        except (OSError, ValueError):
            reasons.append("SOURCE_UNAVAILABLE")
        if scope is not None and _canonical(scope) != _canonical(record["scope"]):
            reasons.append("SCOPE_CHANGED")
        if record["expires_at"] is not None and now >= _time(record["expires_at"]):
            reasons.append("EXPIRED")
        evidence = record["evidence"]
        state = "STALE" if reasons else evidence["evidence_state"]
        units = sorted(set(record["dependent_unit_ids"] + unit_dependencies.get(evidence["id"], [])))
        results.append({"cache_id": record["cache_id"], "evidence_id": evidence["id"],
                        "source_evidence_state": evidence["evidence_state"], "evidence_state": state,
                        "reasons": reasons, "scope": record["scope"], "source": source,
                        "dependent_unit_ids": units,
                        "needs_review_unit_ids": units if state != "CURRENT" else []})
    return {"format_version": "1.0", "report_type": "EVIDENCE_CACHE_CHECK",
            "checked_at": now.isoformat(), "records": results,
            "counts": {state: sum(r["evidence_state"] == state for r in results) for state in sorted(STATES)},
            "needs_review_unit_ids": sorted({u for r in results for u in r["needs_review_unit_ids"]}),
            "review_decision_changes": 0,
            "limitations": ["Hash validity concerns the supplied local source bytes, not live remote-source freshness or semantic correctness.",
                            "Recorded scope is preserved; current scope is compared only when supplied.",
                            "The report proposes affected review scope; human decisions and session evidence are unchanged."]}


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    recorder = commands.add_parser("record")
    recorder.add_argument("--cache", type=Path, required=True)
    recorder.add_argument("--evidence", type=Path, required=True)
    recorder.add_argument("--source", type=Path, required=True)
    recorder.add_argument("--scope", type=Path, required=True)
    recorder.add_argument("--unit-id", action="append", default=[])
    recorder.add_argument("--expires-at")
    checker = commands.add_parser("check")
    checker.add_argument("--cache", type=Path, required=True)
    checker.add_argument("--scope", type=Path)
    checker.add_argument("--session", type=Path)
    checker.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "record":
            record = record_evidence(args.cache, json.loads(_bytes(args.evidence)), args.source,
                                     json.loads(_bytes(args.scope)), args.unit_id, args.expires_at)
            print(json.dumps({"status": "CACHED", "cache_id": record["cache_id"],
                              "evidence_state": record["evidence"]["evidence_state"]}))
        else:
            report = check_cache(args.cache, json.loads(_bytes(args.scope)) if args.scope else None, args.session)
            raw = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
            if args.output:
                if not _new_private(args.output, raw.encode("utf-8")):
                    raise ValueError("Output already exists; select a new report path")
            else:
                print(raw, end="")
            return 0 if all(r["evidence_state"] == "CURRENT" for r in report["records"]) else 2
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(1, "Evidence cache failed: {}\n".format(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

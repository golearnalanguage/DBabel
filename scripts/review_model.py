#!/usr/bin/env python3
"""Core data model and export-gate logic for DBabel Review Workbench.

Designed for Python 3.9+ and the repository's existing jsonschema dependency.
The module never treats a deterministic POTENTIAL_ISSUE as a semantic verdict.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover
    Draft202012Validator = None

REVIEW_STATUSES = {
    "UNREVIEWED",
    "ACCEPT_SUGGESTION",
    "KEEP_CURRENT",
    "USER_EDITED",
    "DEFERRED",
    "BLOCKED",
    "WAIVED",
}
COMPLETED_STATUSES = {"ACCEPT_SUGGESTION", "KEEP_CURRENT", "USER_EDITED", "WAIVED"}
BLOCKING_STATUSES = {"UNREVIEWED", "DEFERRED", "BLOCKED"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("{}:{}: invalid JSON: {}".format(path, lineno, exc))
        if not isinstance(value, dict):
            raise ValueError("{}:{}: expected object".format(path, lineno))
        result.append(value)
    return result


def write_jsonl(path: Path, items: Iterable[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for item in items:
            fh.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")


def append_event(path: Path, event: Dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def load_schema(schema_path: Path) -> Dict[str, Any]:
    return read_json(schema_path)


def validate_against_schema(value: Any, schema_path: Path) -> List[str]:
    if Draft202012Validator is None:
        raise RuntimeError("jsonschema is required for DBabel review contract validation")
    validator = Draft202012Validator(load_schema(schema_path))
    errors = []
    for error in sorted(validator.iter_errors(value), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(x) for x in error.absolute_path)
        errors.append("{}: {}".format(where or "$", error.message))
    return errors


def review_issue_fingerprint(issue: Dict[str, Any]) -> str:
    """Stable fingerprint independent of transient Q0001-style IDs."""
    material = {
        "unit_id": issue.get("unit_id"),
        "kind": issue.get("kind"),
        "label": issue.get("label"),
        "classification": issue.get("classification"),
        "source_items": issue.get("source_items") or [],
        "target_items": issue.get("target_items") or [],
        "glossary_entry_id": issue.get("glossary_entry_id"),
        "suggestion": issue.get("suggestion"),
    }
    return sha256_json(material)


def deterministic_issue_to_review(issue: Dict[str, Any]) -> Dict[str, Any]:
    value = {
        "id": str(issue.get("id") or "QA"),
        "unit_id": str(issue["unit_id"]),
        "kind": "DETERMINISTIC",
        "label": str(issue["check_id"]),
        "severity": str(issue["severity"]),
        "classification": str(issue.get("classification") or "POTENTIAL_ISSUE"),
        "message": str(issue.get("message") or issue["check_id"]),
        "source_items": list(issue.get("source_items") or []),
        "target_items": list(issue.get("target_items") or []),
        "evidence_refs": [],
        "blocking": str(issue.get("severity")) == "ERROR",
    }
    if issue.get("glossary_entry_id"):
        value["glossary_entry_id"] = str(issue["glossary_entry_id"])
    value["fingerprint"] = review_issue_fingerprint(value)
    return value


def semantic_finding_to_review(finding: Dict[str, Any], unit_id: str) -> Dict[str, Any]:
    decision = str(finding.get("decision") or "REVIEW")
    blocking = bool(finding.get("verification_required")) or decision in {"REVIEW", "OUT_OF_SCOPE_CLAIM"}
    confidence = str(finding.get("confidence") or "REVIEW_REQUIRED")
    severity = "REVIEW" if blocking or confidence == "REVIEW_REQUIRED" else "INFO"
    value = {
        "id": str(finding.get("id") or "FINDING"),
        "unit_id": unit_id,
        "kind": "SEMANTIC",
        "label": decision,
        "severity": severity,
        "classification": str(finding.get("classification") or "SEMANTIC"),
        "message": str(finding.get("reason") or decision),
        "evidence_refs": list(finding.get("evidence_refs") or []),
        "blocking": blocking,
    }
    if finding.get("recommendation") is not None:
        value["suggestion"] = str(finding.get("recommendation"))
    value["fingerprint"] = review_issue_fingerprint(value)
    return value


def default_decision(unit_id: str) -> Dict[str, Any]:
    return {
        "unit_id": unit_id,
        "status": "UNREVIEWED",
        "revision": 0,
        "updated_at": utc_now(),
        "reviewer_note": "",
        "waived_issue_fingerprints": [],
        "recheck": {
            "status": "NOT_RUN",
            "error_count": 0,
            "warning_count": 0,
            "issue_fingerprints": [],
        },
    }


def final_target_for(unit: Dict[str, Any], decision: Dict[str, Any]) -> str:
    status = decision.get("status")
    if status in COMPLETED_STATUSES:
        if "approved_target" not in decision:
            raise ValueError("completed decision for {} has no approved_target".format(unit["id"]))
        return str(decision["approved_target"])
    return str(unit.get("current_target") or "")


def normalize_decision(unit: Dict[str, Any], incoming: Dict[str, Any], previous: Dict[str, Any]) -> Dict[str, Any]:
    status = str(incoming.get("status") or "")
    if status not in REVIEW_STATUSES:
        raise ValueError("unsupported review status: {}".format(status))
    value = default_decision(unit["id"])
    value["status"] = status
    value["revision"] = int(previous.get("revision", 0)) + 1
    value["updated_at"] = utc_now()
    value["reviewer_note"] = str(incoming.get("reviewer_note") or "")
    value["waived_issue_fingerprints"] = sorted(set(str(x) for x in incoming.get("waived_issue_fingerprints") or []))
    if status == "ACCEPT_SUGGESTION":
        suggestion = unit.get("suggested_target")
        if suggestion is None:
            raise ValueError("unit {} has no suggested_target".format(unit["id"]))
        value["approved_target"] = str(suggestion)
    elif status == "KEEP_CURRENT":
        value["approved_target"] = str(unit.get("current_target") or "")
    elif status in {"USER_EDITED", "WAIVED"}:
        if "approved_target" not in incoming:
            raise ValueError("{} requires approved_target".format(status))
        value["approved_target"] = str(incoming["approved_target"])
    if status == "WAIVED":
        reason = str(incoming.get("waiver_reason") or "").strip()
        if not reason:
            raise ValueError("WAIVED requires waiver_reason")
        value["waiver_reason"] = reason
    # A material target change invalidates prior QA state until fresh recheck.
    if value.get("approved_target") == previous.get("approved_target") and incoming.get("recheck"):
        value["recheck"] = incoming["recheck"]
    return value


def load_bundle(bundle: Path) -> Dict[str, Any]:
    bundle = bundle.resolve()
    if not bundle.is_dir():
        raise ValueError("review bundle is not a directory: {}".format(bundle))
    session = read_json(bundle / "session.json")
    units = read_jsonl(bundle / "units.jsonl")
    issues = read_json(bundle / "issues.json")
    evidence = read_json(bundle / "evidence.json")
    decisions = read_json(bundle / "decisions.json")
    anchors = read_json(bundle / "anchors.json")
    events = read_jsonl(bundle / "events.jsonl")
    if not isinstance(issues, list) or not isinstance(evidence, list) or not isinstance(decisions, list):
        raise ValueError("issues/evidence/decisions must be JSON arrays")
    by_unit = {x["id"]: x for x in units}
    by_decision = {x["unit_id"]: x for x in decisions}
    if len(by_unit) != len(units):
        raise ValueError("duplicate review unit IDs")
    if len(by_decision) != len(decisions):
        raise ValueError("duplicate decision unit IDs")
    missing = sorted(set(by_unit) - set(by_decision))
    extra = sorted(set(by_decision) - set(by_unit))
    if missing or extra:
        raise ValueError("decision coverage mismatch: missing={} extra={}".format(missing, extra))
    return {
        "bundle": bundle,
        "session": session,
        "units": units,
        "issues": issues,
        "evidence": evidence,
        "decisions": decisions,
        "anchors": anchors,
        "events": events,
        "units_by_id": by_unit,
        "decisions_by_id": by_decision,
    }


def save_decisions(bundle: Path, decisions: Sequence[Dict[str, Any]]) -> None:
    target = bundle / "decisions.json"
    temporary = bundle / ".decisions.json.tmp"

    try:
        write_json(
            temporary,
            list(decisions),
        )
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()


def progress(bundle_data: Dict[str, Any]) -> Dict[str, int]:
    decisions = bundle_data["decisions"]
    result = {status: 0 for status in REVIEW_STATUSES}
    for d in decisions:
        result[d["status"]] += 1
    result["TOTAL"] = len(decisions)
    result["COMPLETED"] = sum(result[s] for s in COMPLETED_STATUSES)
    result["REMAINING"] = result["TOTAL"] - result["COMPLETED"]
    return result


def _load_accuracy_core_module(repo_root: Path):
    path = repo_root / "scripts" / "check_bilingual_integrity.py"
    if not path.exists():
        raise RuntimeError("Accuracy Core script not found: {}".format(path))
    spec = importlib.util.spec_from_file_location("dbabel_accuracy_core", str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load Accuracy Core")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def default_qa_runner(
    repo_root: Path,
    unit: Dict[str, Any],
    final_target: str,
    glossary_path: Optional[Path] = None,
) -> Dict[str, Any]:
    core = _load_accuracy_core_module(repo_root)
    config = core.load_config(str(repo_root / "config" / "deterministic_qa.yaml"))
    glossary = None
    if glossary_path is not None:
        glossary = core._load_glossary(str(glossary_path))
    qa_unit = {
        "id": unit["id"],
        "source": unit.get("source") or "",
        "target": final_target,
    }
    for key in ("location", "source_language", "target_language", "context"):
        if key in unit:
            qa_unit[key] = unit[key]
    report = core.run_qa([qa_unit], config, glossary)
    converted = [deterministic_issue_to_review(x) for x in report.get("issues") or []]
    return {
        "summary": report["summary"],
        "issues": converted,
        "raw": report,
    }


def recheck_decision(
    repo_root: Path,
    unit: Dict[str, Any],
    decision: Dict[str, Any],
    glossary_path: Optional[Path] = None,
    qa_runner: Optional[Callable[[Path, Dict[str, Any], str, Optional[Path]], Dict[str, Any]]] = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    qa_runner = qa_runner or default_qa_runner
    target = final_target_for(unit, decision)
    result = qa_runner(repo_root, unit, target, glossary_path)
    issues = result.get("issues") or []
    errors = sum(1 for x in issues if x.get("severity") == "ERROR")
    warnings = sum(1 for x in issues if x.get("severity") == "WARNING")
    updated = dict(decision)
    updated["recheck"] = {
        "status": "FAIL" if errors else "PASS",
        "error_count": errors,
        "warning_count": warnings,
        "issue_fingerprints": sorted({x["fingerprint"] for x in issues}),
    }
    return updated, issues


def evaluate_export_gate(
    bundle_data: Dict[str, Any],
    fresh_qa_by_unit: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    original_path: Optional[Path] = None,
) -> Dict[str, Any]:
    session = bundle_data["session"]
    units_by_id = bundle_data["units_by_id"]
    decisions_by_id = bundle_data["decisions_by_id"]
    issues = bundle_data["issues"]
    blockers: List[str] = []
    waivers: List[Dict[str, str]] = []

    if original_path is not None:
        if not original_path.exists():
            blockers.append("original file does not exist: {}".format(original_path))
        else:
            actual = sha256_file(original_path)
            expected = session["original"]["sha256"]
            if actual != expected:
                blockers.append("original file SHA-256 changed")

    static_by_unit: Dict[str, List[Dict[str, Any]]] = {}
    for issue in issues:
        static_by_unit.setdefault(issue["unit_id"], []).append(issue)

    for unit_id, unit in units_by_id.items():
        decision = decisions_by_id[unit_id]
        status = decision["status"]

        alignment = str(
            unit.get("alignment") or "ALIGNED"
        )

        if alignment != "ALIGNED":
            blockers.append(
                "{} alignment is {}; native export requires "
                "ALIGNED".format(
                    unit_id,
                    alignment,
                )
            )

        if unit.get("requires_confirmation", True) and status in BLOCKING_STATUSES:
            blockers.append("{} is {}".format(unit_id, status))
            continue
        if status == "USER_EDITED" and decision.get("recheck", {}).get("status") == "NOT_RUN":
            blockers.append("{} USER_EDITED has not been rechecked".format(unit_id))
        if fresh_qa_by_unit is not None:
            semantic_static = [x for x in static_by_unit.get(unit_id, []) if x.get("kind") == "SEMANTIC"]
            relevant = semantic_static + list(fresh_qa_by_unit.get(unit_id, []))
        else:
            relevant = static_by_unit.get(unit_id, [])
        fingerprints = set(decision.get("waived_issue_fingerprints") or [])
        for issue in relevant:
            if issue.get("severity") != "ERROR" or not issue.get("blocking", True):
                continue
            fp = issue["fingerprint"]
            if status == "WAIVED" and fp in fingerprints and str(decision.get("waiver_reason") or "").strip():
                waivers.append({
                    "unit_id": unit_id,
                    "fingerprint": fp,
                    "reason": str(decision["waiver_reason"]),
                })
            else:
                blockers.append("{} has unwaived ERROR {}".format(unit_id, issue.get("label") or issue["id"]))

    decisions_canonical = [decisions_by_id[k] for k in sorted(decisions_by_id)]
    qa_summary = {"units_checked": len(units_by_id), "error_count": 0, "warning_count": 0}
    if fresh_qa_by_unit is not None:
        all_issues = [x for values in fresh_qa_by_unit.values() for x in values]
        qa_summary["error_count"] = sum(1 for x in all_issues if x.get("severity") == "ERROR")
        qa_summary["warning_count"] = sum(1 for x in all_issues if x.get("severity") == "WARNING")
    else:
        qa_summary["error_count"] = sum(1 for x in issues if x.get("severity") == "ERROR")
        qa_summary["warning_count"] = sum(1 for x in issues if x.get("severity") == "WARNING")

    return {
        "format_version": "1.0",
        "session_id": session["session_id"],
        "status": "BLOCKED" if blockers else "AUTHORIZED",
        "checked_at": utc_now(),
        "source_sha256": session["original"]["sha256"],
        "decision_digest": sha256_json(decisions_canonical),
        "blockers": sorted(set(blockers)),
        "waivers": waivers,
        "qa_summary": qa_summary,
        "round_trip": {"status": "NOT_RUN", "checks": []},
    }


def fresh_recheck_all(
    bundle_data: Dict[str, Any],
    repo_root: Path,
    glossary_path: Optional[Path] = None,
    qa_runner: Optional[Callable[[Path, Dict[str, Any], str, Optional[Path]], Dict[str, Any]]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    updated_decisions: List[Dict[str, Any]] = []
    qa_by_unit: Dict[str, List[Dict[str, Any]]] = {}
    for unit in bundle_data["units"]:
        decision = bundle_data["decisions_by_id"][unit["id"]]
        if decision["status"] in COMPLETED_STATUSES:
            updated, issues = recheck_decision(repo_root, unit, decision, glossary_path, qa_runner)
            updated_decisions.append(updated)
            qa_by_unit[unit["id"]] = issues
        else:
            updated_decisions.append(decision)
            qa_by_unit[unit["id"]] = []
    return updated_decisions, qa_by_unit


def schema_root_from_repo(repo_root: Path) -> Path:
    return repo_root / "schemas"


def validate_bundle(bundle: Path, repo_root: Path) -> List[str]:
    data = load_bundle(bundle)
    schemas = schema_root_from_repo(repo_root)
    errors: List[str] = []
    for rel, value in [
        ("review_session.schema.json", data["session"]),
        ("review_issue.schema.json", None),
        ("review_decision.schema.json", None),
        ("review_unit.schema.json", None),
    ]:
        schema_path = schemas / rel
        if not schema_path.exists():
            errors.append("missing schema {}".format(schema_path))
            continue
        if value is not None:
            errors.extend("{} {}".format(rel, x) for x in validate_against_schema(value, schema_path))
    if (schemas / "review_unit.schema.json").exists():
        for unit in data["units"]:
            errors.extend("unit {} {}".format(unit.get("id"), x) for x in validate_against_schema(unit, schemas / "review_unit.schema.json"))
    if (schemas / "review_issue.schema.json").exists():
        for issue in data["issues"]:
            errors.extend("issue {} {}".format(issue.get("id"), x) for x in validate_against_schema(issue, schemas / "review_issue.schema.json"))
    if (schemas / "review_decision.schema.json").exists():
        for decision in data["decisions"]:
            errors.extend("decision {} {}".format(decision.get("unit_id"), x) for x in validate_against_schema(decision, schemas / "review_decision.schema.json"))
    if (schemas / "review_event.schema.json").exists():
        for index, event in enumerate(data["events"], 1):
            errors.extend("event {} {}".format(index, x) for x in validate_against_schema(event, schemas / "review_event.schema.json"))
    checksum_file = bundle / "original.sha256"
    if checksum_file.exists():
        first = checksum_file.read_text(encoding="utf-8").strip().split()
        if not first or first[0] != data["session"]["original"]["sha256"]:
            errors.append("original.sha256 does not match session.json")
    return errors

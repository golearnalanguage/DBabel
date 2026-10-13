"""One exact applicability identity for local translation assets.

Missing metadata is unknown, never a wildcard. Old unscoped records remain
manageable but cannot supply automatic translations or rejection constraints.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, Mapping, Optional

SCOPE_FIELDS = ("project_id", "vendor", "product", "version", "domain", "text_role")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


def _context(value: Any) -> Dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("translation memory context must be an object")
    result = {}
    for name in SCOPE_FIELDS:
        item = value.get(name)
        if item is None:
            continue
        if not isinstance(item, str) or not item.strip():
            raise ValueError("translation memory context {} must be nonempty text".format(name))
        result[name] = item.strip()
    return result


def with_scope(unit: Mapping[str, Any], *, context: Optional[Mapping[str, Any]] = None,
               document_sha256: Optional[str] = None) -> Dict[str, Any]:
    """Copy a unit, preserving its narrower context over document defaults."""
    result = dict(unit)
    combined = _context(context)
    combined.update(_context(unit.get("context")))
    role = unit.get("text_role") or combined.get("text_role") or "PROSE"
    if not isinstance(role, str) or not role.strip():
        raise ValueError("translation memory text role must be nonempty text")
    if combined.get("text_role") and combined["text_role"] != role.strip():
        raise ValueError("translation memory text roles disagree")
    combined["text_role"] = role.strip()
    if "project_id" not in combined and document_sha256 is not None:
        if not isinstance(document_sha256, str) or not _DIGEST.fullmatch(document_sha256):
            raise ValueError("translation memory document SHA-256 is invalid")
        combined["project_id"] = "document:" + document_sha256
    result["context"] = combined
    return result


def canonical_scope(unit: Mapping[str, Any], document_sha256: Optional[str] = None) -> Dict[str, Any]:
    context = with_scope(unit, document_sha256=document_sha256)["context"]
    project = context.get("project_id")
    if project is None:
        kind = "LEGACY_UNSCOPED"
    elif project.startswith("document:") and _DIGEST.fullmatch(project[9:]):
        kind = "DOCUMENT"
    else:
        kind = "SCOPED"
    identity = {"kind": kind, "context": context}
    encoded = json.dumps(identity, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return {"key": hashlib.sha256(encoded).hexdigest(), "kind": kind,
            "context": context, "automatic": kind != "LEGACY_UNSCOPED"}


def scopes_equal(left: Mapping[str, Any], right: Mapping[str, Any],
                 document_sha256: Optional[str] = None) -> bool:
    return canonical_scope(left, document_sha256)["key"] == canonical_scope(right, document_sha256)["key"]


def record_applies(record: Mapping[str, Any], unit: Mapping[str, Any]) -> bool:
    """Match a rejection or exported asset without trusting a supplied hash."""
    scope = record.get("memory_scope") or record.get("applicability")
    # Exported SQLite rows use `scope`; rejection JSON already uses that name
    # for TERM/SEGMENT matching, so its applicability lives in memory_scope.
    if scope is None and isinstance(record.get("scope"), Mapping):
        scope = record["scope"]
    if not isinstance(scope, Mapping) or scope.get("kind") == "LEGACY_UNSCOPED":
        return False
    expected = canonical_scope({"context": scope.get("context")})
    selected = canonical_scope(unit)
    return (expected["automatic"] and selected["automatic"]
            and expected["key"] == selected["key"]
            and scope.get("key", expected["key"]) == expected["key"])

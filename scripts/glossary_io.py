#!/usr/bin/env python3
"""Load and validate DBabel project glossaries in canonical JSON or CSV form."""
from __future__ import annotations

import csv
import json
import unicodedata
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "project_glossary.schema.json"

CSV_COLUMNS = [
    "entry_id",
    "source_language",
    "source_term",
    "behavior",
    "approval",
    "target_language",
    "preferred_target",
    "admitted_targets",
    "forbidden_targets",
    "vendor",
    "product",
    "version",
    "domain",
    "text_roles",
    "match_mode",
    "case_sensitive",
    "notes",
]


class GlossaryError(ValueError):
    """Raised when a project glossary cannot be parsed or validated safely."""


class GlossaryConflictError(GlossaryError):
    """Raised when approved glossary scope cannot be resolved deterministically."""


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _split_multi(value: str) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(";") if item.strip()]


def _parse_bool(value: str, field: str, row_number: int) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise GlossaryError(
        "CSV row {}: {} must be 'true' or 'false', got {!r}".format(
            row_number, field, value
        )
    )


def _dedupe_preserve(values: Iterable[str]) -> List[str]:
    seen = set()
    out = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _csv_row_to_entry(row: Mapping[str, str], row_number: int) -> dict:
    def value(name: str) -> str:
        raw = row.get(name)
        return "" if raw is None else raw.strip()

    entry_id = value("entry_id")
    source_language = value("source_language")
    source_term = value("source_term")
    behavior = value("behavior")
    approval = value("approval")
    match_mode = value("match_mode")
    case_sensitive = _parse_bool(value("case_sensitive"), "case_sensitive", row_number)

    preferred = value("preferred_target")
    admitted = _split_multi(value("admitted_targets"))
    forbidden = _split_multi(value("forbidden_targets"))
    target_language = value("target_language")

    target_terms = []
    if preferred:
        target_terms.append((preferred, "PREFERRED"))
    target_terms.extend((term, "ADMITTED") for term in admitted)
    target_terms.extend((term, "FORBIDDEN") for term in forbidden)

    if target_terms and not target_language:
        raise GlossaryError(
            "CSV row {}: target_language is required when target terms are present".format(
                row_number
            )
        )

    targets = [
        {"language": target_language, "term": term, "status": status}
        for term, status in target_terms
    ]

    scope = {}
    for field in ("vendor", "product", "version", "domain"):
        if value(field):
            scope[field] = value(field)
    roles = _dedupe_preserve(_split_multi(value("text_roles")))
    if roles:
        scope["text_roles"] = roles

    entry = {
        "id": entry_id,
        "source": {"language": source_language, "term": source_term},
        "behavior": behavior,
        "approval": approval,
        "targets": targets,
        "scope": scope,
        "match": {
            "mode": match_mode,
            "case_sensitive": case_sensitive,
            "unicode_normalization": "NFC",
        },
    }
    if value("notes"):
        entry["notes"] = value("notes")
    return entry


def load_csv(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise GlossaryError("CSV has no header")
        fieldnames = list(reader.fieldnames)
        if fieldnames != CSV_COLUMNS:
            raise GlossaryError(
                "CSV header mismatch: expected exactly {}".format(",".join(CSV_COLUMNS))
            )

        entries = []
        for row_number, row in enumerate(reader, start=2):
            if row is None:
                continue
            if all(not (value or "").strip() for value in row.values()):
                continue
            entries.append(_csv_row_to_entry(row, row_number))

    return {"format_version": "1.0", "entries": entries}


def load_glossary(path_like) -> dict:
    path = Path(path_like)
    suffix = path.suffix.lower()
    try:
        if suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
        elif suffix == ".csv":
            data = load_csv(path)
        else:
            raise GlossaryError(
                "unsupported glossary format {!r}; use .json or .csv".format(suffix)
            )
    except (OSError, UnicodeError, json.JSONDecodeError, csv.Error) as exc:
        raise GlossaryError("{}: {}".format(path, exc))

    errors = validate_glossary(data)
    if errors:
        raise GlossaryError("\n".join(errors))
    return data


def _normalize(value: str, mode: str, case_sensitive: bool) -> str:
    if mode == "NFC":
        value = unicodedata.normalize("NFC", value)
    if not case_sensitive:
        value = value.casefold()
    return value


def _target_key(entry: dict, target: dict) -> Tuple[str, str]:
    match = entry["match"]
    term = _normalize(
        target["term"], match["unicode_normalization"], match["case_sensitive"]
    )
    return target["language"], term


def _entry_identity(entry: dict) -> Tuple:
    match = entry["match"]
    source_term = _normalize(
        entry["source"]["term"],
        match["unicode_normalization"],
        match["case_sensitive"],
    )
    scope = entry.get("scope", {})
    roles = tuple(sorted(scope.get("text_roles", [])))
    return (
        entry["source"]["language"],
        source_term,
        match["mode"],
        match["case_sensitive"],
        match["unicode_normalization"],
        scope.get("vendor"),
        scope.get("product"),
        scope.get("version"),
        scope.get("domain"),
        roles,
    )


def validate_glossary(data: object) -> List[str]:
    errors = []
    validator = Draft202012Validator(_schema())
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path)):
        location = "$"
        for part in err.absolute_path:
            location += "[{}]".format(part) if isinstance(part, int) else ".{}".format(part)
        errors.append("{}: {}".format(location, err.message))

    if errors or not isinstance(data, dict):
        return errors

    entries = data.get("entries", [])
    seen_ids: Dict[str, int] = {}
    seen_identity: Dict[Tuple, Tuple[int, str]] = {}

    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        entry_id = entry.get("id")
        if entry_id in seen_ids:
            errors.append(
                "$.entries[{}].id: duplicate entry id {!r}; first used at index {}".format(
                    index, entry_id, seen_ids[entry_id]
                )
            )
        elif isinstance(entry_id, str):
            seen_ids[entry_id] = index

        if not all(key in entry for key in ("source", "match", "scope", "targets")):
            continue

        target_statuses: Dict[Tuple[str, str], set] = {}
        for target in entry.get("targets", []):
            if not isinstance(target, dict) or not all(
                key in target for key in ("language", "term", "status")
            ):
                continue
            key = _target_key(entry, target)
            target_statuses.setdefault(key, set()).add(target["status"])

        for key, statuses in target_statuses.items():
            if "FORBIDDEN" in statuses and statuses.intersection({"PREFERRED", "ADMITTED"}):
                errors.append(
                    "$.entries[{}].targets: designation {!r} is both allowed and forbidden".format(
                        index, key[1]
                    )
                )

        if entry.get("behavior") == "PROTECT" and not entry.get("match", {}).get("case_sensitive", False):
            errors.append(
                "$.entries[{}].match.case_sensitive: PROTECT entries must be case-sensitive so literal preservation is deterministic".format(index)
            )

        if entry.get("approval") == "PROJECT_APPROVED":
            identity = _entry_identity(entry)
            if identity in seen_identity:
                first_index, first_id = seen_identity[identity]
                errors.append(
                    "$.entries[{}]: approved entry {!r} duplicates the same source/match/scope as {!r} at index {}; consolidate targets into one entry".format(
                        index, entry_id, first_id, first_index
                    )
                )
            else:
                seen_identity[identity] = (index, entry_id)

    return errors


def normalize_text(text: str, entry: dict) -> str:
    match = entry["match"]
    return _normalize(text, match["unicode_normalization"], match["case_sensitive"])


def _is_boundary_word_char(char: str) -> bool:
    """Use identifier-style boundaries for ASCII terms; CJK text is unspaced."""
    return bool(char) and char.isascii() and (char.isalnum() or char == "_")


def term_occurrences(text: str, term: str, entry: dict) -> int:
    """Count conservative exact/token matches under an entry's declared policy."""
    normalized_text = normalize_text(text, entry)
    normalized_term = normalize_text(term, entry)
    if not normalized_term:
        return 0

    if entry["match"]["mode"] == "exact":
        return int(normalized_text == normalized_term)

    count = 0
    start = 0
    while True:
        pos = normalized_text.find(normalized_term, start)
        if pos < 0:
            break
        left = normalized_text[pos - 1] if pos > 0 else ""
        right_pos = pos + len(normalized_term)
        right = normalized_text[right_pos] if right_pos < len(normalized_text) else ""
        first = normalized_term[0]
        last = normalized_term[-1]
        left_ok = not (_is_boundary_word_char(first) and _is_boundary_word_char(left))
        right_ok = not (_is_boundary_word_char(last) and _is_boundary_word_char(right))
        if left_ok and right_ok:
            count += 1
        start = pos + max(1, len(normalized_term))
    return count


def scope_matches(entry: dict, unit: dict) -> bool:
    scope = entry.get("scope", {})
    context = unit.get("context") or {}
    for field in ("vendor", "product", "version", "domain"):
        if field in scope:
            if field not in context or context[field] != scope[field]:
                return False
    roles = scope.get("text_roles")
    if roles:
        current_role = context.get("text_role")
        if current_role is None or current_role not in roles:
            return False
    return True


def language_matches(entry: dict, unit: dict) -> bool:
    source_language = unit.get("source_language")
    if source_language and source_language != entry["source"]["language"]:
        return False
    return True


def _scope_more_specific(a: dict, b: dict) -> bool:
    """Return True when scope a is a strict narrowing of compatible scope b."""
    sa = a.get("scope", {})
    sb = b.get("scope", {})
    stricter = False
    for field in ("vendor", "product", "version", "domain"):
        bv = sb.get(field)
        av = sa.get(field)
        if bv is not None and av != bv:
            return False
        if bv is None and av is not None:
            stricter = True

    br = set(sb.get("text_roles", []))
    ar = set(sa.get("text_roles", []))
    if br:
        if not ar or not ar.issubset(br):
            return False
        if ar != br:
            stricter = True
    elif ar:
        stricter = True
    return stricter


def _source_group_key(entry: dict) -> Tuple:
    # Group the same lexical source designation even when entries declare different
    # matching policies. If both policies match one unit, scope precedence must be
    # resolved before either rule can be enforced.
    term = unicodedata.normalize("NFC", entry["source"]["term"]).casefold()
    return (entry["source"]["language"], term)


def applicable_entries(glossary: Optional[dict], unit: dict) -> List[dict]:
    if not glossary:
        return []
    matched = []
    for entry in glossary.get("entries", []):
        if entry.get("approval") != "PROJECT_APPROVED":
            continue
        if not language_matches(entry, unit):
            continue
        if not scope_matches(entry, unit):
            continue
        if term_occurrences(unit["source"], entry["source"]["term"], entry) < 1:
            continue
        matched.append(entry)

    groups: Dict[Tuple, List[dict]] = {}
    for entry in matched:
        groups.setdefault(_source_group_key(entry), []).append(entry)

    selected = []
    for group in groups.values():
        maximal = [
            entry
            for entry in group
            if not any(
                other is not entry and _scope_more_specific(other, entry)
                for other in group
            )
        ]
        if len(maximal) > 1:
            ids = ", ".join(sorted(entry["id"] for entry in maximal))
            raise GlossaryConflictError(
                "unit {!r}: multiple incomparable PROJECT_APPROVED glossary entries apply to source term {!r}: {}; narrow or consolidate their scopes before deterministic QA".format(
                    unit.get("id"), maximal[0]["source"]["term"], ids
                )
            )
        selected.extend(maximal)
    return selected


def targets_for_unit(entry: dict, unit: dict) -> List[dict]:
    targets = entry.get("targets", [])
    target_language = unit.get("target_language")
    if target_language:
        return [target for target in targets if target["language"] == target_language]
    languages = {target["language"] for target in targets}
    if len(languages) <= 1:
        return list(targets)
    return []

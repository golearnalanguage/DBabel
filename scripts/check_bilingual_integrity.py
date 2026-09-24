#!/usr/bin/env python3
"""Deterministic bilingual integrity checks for aligned text units.

This tool reports mechanical differences as POTENTIAL_ISSUE records. It does not
establish semantic error and never authorizes repair.
"""
import argparse
from collections import Counter
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
import sys
import unicodedata

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "deterministic_qa.yaml"
UNIT_SCHEMA = ROOT / "schemas" / "bilingual_unit.schema.json"
REPORT_SCHEMA = ROOT / "schemas" / "deterministic_qa_report.schema.json"

PLACEHOLDER_RE = re.compile(
    r"(?<!\$)\{\{[^{}\n]+\}\}|(?<!\$)\{[A-Za-z_][A-Za-z0-9_.-]*\}|"
    r"(?<!\$)\{\d+\}|%(?:\d+\$)?[A-Za-z]"
)
URL_RE = re.compile(r"(?i)\b(?:https?|ftp)://[^\s<>\"']+")
WINDOWS_PATH_RE = re.compile(r"(?<![A-Za-z0-9_])(?:[A-Za-z]:\\(?:[^\\/:*?\"<>|\r\n]+\\)*[^\\/:*?\"<>|\r\n]*)")
UNIX_PATH_RE = re.compile(r"(?<![:A-Za-z0-9_])/(?:[^\s/]+/)*[^\s/]+")
FILENAME_RE = re.compile(r"(?<![\w./\\-])(?:[A-Za-z0-9_.-]+\.[A-Za-z][A-Za-z0-9]{0,9})(?![\w/\\-])")
CLI_RE = re.compile(r"(?<![\w-])--?[A-Za-z][A-Za-z0-9_-]*")
ENV_RE = re.compile(r"\$[A-Z_][A-Z0-9_]*|\$\{[A-Z_][A-Z0-9_]*\}|%[A-Z_][A-Z0-9_]*%")
VERSION_RE = re.compile(r"(?i)(?:\bversion\s+|\bver(?:sion)?\.?\s*|\bv)(\d+(?:\.\d+){1,3})(?!\d)")
NUMBER_RE = re.compile(r"(?<![\w.])[-+]?\d(?:[\d\s\u00A0\u202F,.]*\d)?(?![\w.])")
TRAILING_URL_PUNCT = ".,;:!?)]}>，。；：！？）》】」』"


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_units(path):
    """Load a JSON array, one JSON object, or JSONL bilingual units."""
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    stripped = text.lstrip()
    if not stripped:
        return []
    if stripped.startswith("["):
        value = json.loads(text)
        if not isinstance(value, list):
            raise ValueError("bilingual-unit JSON root must be an array")
        return value
    if stripped.startswith("{"):
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            value = None
        if isinstance(value, dict):
            return [value]
        if value is not None:
            raise ValueError("bilingual-unit JSON must be an object")
    units = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError("{}:{}: invalid JSON: {}".format(p, lineno, exc))
        if not isinstance(value, dict):
            raise ValueError("{}:{}: unit must be an object".format(p, lineno))
        units.append(value)
    return units


def load_config(path=DEFAULT_CONFIG):
    value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("deterministic QA config root must be a mapping")
    return value


def validate_units(units, schema_path=UNIT_SCHEMA):
    schema = _read_json(schema_path)
    validator = Draft202012Validator(schema)
    errors = []
    seen = set()
    for index, unit in enumerate(units):
        prefix = "unit[{}]".format(index)
        for error in sorted(validator.iter_errors(unit), key=lambda e: list(e.path)):
            loc = ".".join(str(x) for x in error.path)
            errors.append("{}{}: {}".format(prefix, "." + loc if loc else "", error.message))
        unit_id = unit.get("id") if isinstance(unit, dict) else None
        if unit_id in seen:
            errors.append("{}: duplicate unit id {!r}".format(prefix, unit_id))
        if unit_id is not None:
            seen.add(unit_id)
        if isinstance(unit, dict) and unit.get("alignment") == "AMBIGUOUS":
            errors.append("{}: alignment is AMBIGUOUS; deterministic QA requires aligned units".format(prefix))
    return errors


def _normalize_text(text, normalization, case_sensitive):
    if normalization == "NFC":
        text = unicodedata.normalize("NFC", text)
    if not case_sensitive:
        text = text.casefold()
    return text


def _contains_term(text, term, mode="token", case_sensitive=False, normalization="NFC"):
    hay = _normalize_text(text, normalization, case_sensitive)
    needle = _normalize_text(term, normalization, case_sensitive)
    if not needle:
        return False
    if mode == "exact":
        return hay == needle
    if mode != "token":
        raise ValueError("unsupported match mode {!r}".format(mode))
    # CJK and other scripts commonly do not use spaces. Substring matching is more
    # faithful than ASCII word-boundary semantics for those terms.
    if any(ord(ch) > 127 and ch.isalnum() for ch in needle):
        return needle in hay
    left = r"(?<![A-Za-z0-9_])"
    right = r"(?![A-Za-z0-9_])"
    return re.search(left + re.escape(needle) + right, hay) is not None


def _scope_applies(entry, unit):
    scope = entry.get("scope") or {}
    context = unit.get("context") or {}
    for field in ("vendor", "product", "version", "domain"):
        wanted = scope.get(field)
        if wanted is not None:
            actual = context.get(field)
            if actual is None or actual != wanted:
                return False
    roles = scope.get("text_roles") or []
    if roles:
        actual_role = context.get("text_role")
        if actual_role is None or actual_role not in roles:
            return False
    return True


def _approved_entries(glossary):
    if not glossary:
        return []
    return [entry for entry in glossary.get("entries", []) if entry.get("approval") == "PROJECT_APPROVED"]


def _strip_url_punctuation(value):
    while value and value[-1] in TRAILING_URL_PUNCT:
        value = value[:-1]
    return value


def extract_urls(text):
    return [_strip_url_punctuation(m.group(0)) for m in URL_RE.finditer(text)]


def _mask_spans(text, spans):
    chars = list(text)
    for start, end in spans:
        for i in range(start, end):
            chars[i] = " "
    return "".join(chars)


def _url_spans(text):
    return [(m.start(), m.end()) for m in URL_RE.finditer(text)]


def extract_paths(text):
    masked = _mask_spans(text, _url_spans(text))
    values = [m.group(0).rstrip(".,;:!?)]}>，。；：！？）》】」』") for m in WINDOWS_PATH_RE.finditer(masked)]
    values.extend(m.group(0).rstrip(".,;:!?)]}>，。；：！？）》】」』") for m in UNIX_PATH_RE.finditer(masked))
    return [x for x in values if x]


def extract_filenames(text):
    masked = _mask_spans(text, _url_spans(text))
    # Paths are handled by PATH_INTEGRITY; hide them before standalone filename scan.
    spans = []
    for regex in (WINDOWS_PATH_RE, UNIX_PATH_RE):
        spans.extend((m.start(), m.end()) for m in regex.finditer(masked))
    masked = _mask_spans(masked, spans)
    return [m.group(0) for m in FILENAME_RE.finditer(masked)]


def extract_placeholders(text):
    return [m.group(0) for m in PLACEHOLDER_RE.finditer(text)]


def extract_cli_options(text):
    return [m.group(0) for m in CLI_RE.finditer(text)]


def extract_env_vars(text):
    return [m.group(0) for m in ENV_RE.finditer(text)]


def extract_versions(text):
    return [m.group(1) for m in VERSION_RE.finditer(text)]


def _number_candidates(token):
    s = token.replace("\u00a0", "").replace("\u202f", "").replace(" ", "")
    if not s:
        return set()
    sign = ""
    if s[0] in "+-":
        sign, s = s[0], s[1:]
    if not s or not re.fullmatch(r"\d[\d,.]*", s):
        return set()
    results = set()
    if "," in s and "." in s:
        last_comma = s.rfind(",")
        last_dot = s.rfind(".")
        decimal_sep = "," if last_comma > last_dot else "."
        grouping_sep = "." if decimal_sep == "," else ","
        canonical = s.replace(grouping_sep, "").replace(decimal_sep, ".")
        try:
            results.add(Decimal(sign + canonical))
        except InvalidOperation:
            pass
        return results
    for sep in (",", "."):
        if sep not in s:
            continue
        parts = s.split(sep)
        if all(part.isdigit() for part in parts):
            # Decimal interpretation is always possible for a single separator.
            if len(parts) == 2:
                try:
                    results.add(Decimal(sign + parts[0] + "." + parts[1]))
                except InvalidOperation:
                    pass
            # Grouping interpretation is possible for groups of three digits.
            if len(parts) > 1 and all(len(part) == 3 for part in parts[1:]):
                try:
                    results.add(Decimal(sign + "".join(parts)))
                except InvalidOperation:
                    pass
        return results
    try:
        results.add(Decimal(sign + s))
    except InvalidOperation:
        pass
    return results


def _numeric_equivalent(source_token, target_token):
    return bool(_number_candidates(source_token) & _number_candidates(target_token))


def extract_number_units(text, unit_allowlist):
    if not unit_allowlist:
        return []
    unit_pattern = "|".join(sorted((re.escape(x) for x in unit_allowlist), key=len, reverse=True))
    regex = re.compile(
        r"(?<![\w.])([-+]?\d(?:[\d\s\u00A0\u202F,.]*\d)?)\s*(" + unit_pattern + r")(?![A-Za-z])"
    )
    return [(m.group(1), m.group(2)) for m in regex.finditer(text)]


def _protected_numeric_spans(text, unit_allowlist):
    spans = _url_spans(text)
    for regex in (WINDOWS_PATH_RE, UNIX_PATH_RE, PLACEHOLDER_RE, VERSION_RE):
        spans.extend((m.start(), m.end()) for m in regex.finditer(text))
    if unit_allowlist:
        unit_pattern = "|".join(sorted((re.escape(x) for x in unit_allowlist), key=len, reverse=True))
        unit_regex = re.compile(
            r"(?<![\w.])[-+]?\d(?:[\d\s\u00A0\u202F,.]*\d)?\s*(?:" + unit_pattern + r")(?![A-Za-z])"
        )
        spans.extend((m.start(), m.end()) for m in unit_regex.finditer(text))
    return spans


def extract_plain_numbers(text, unit_allowlist):
    masked = _mask_spans(text, _protected_numeric_spans(text, unit_allowlist))
    return [m.group(0).strip() for m in NUMBER_RE.finditer(masked)]


def _counter_diff(source_items, target_items):
    source = Counter(source_items)
    target = Counter(target_items)
    missing = list((source - target).elements())
    extra = list((target - source).elements())
    return missing, extra


def _numeric_multiset_diff(source_items, target_items):
    unmatched_target = list(target_items)
    missing = []
    for s in source_items:
        match_index = None
        for index, t in enumerate(unmatched_target):
            if _numeric_equivalent(s, t):
                match_index = index
                break
        if match_index is None:
            missing.append(s)
        else:
            unmatched_target.pop(match_index)
    return missing, unmatched_target


def _number_unit_diff(source_items, target_items):
    unmatched_target = list(target_items)
    missing = []
    for source_number, source_unit in source_items:
        match_index = None
        for index, (target_number, target_unit) in enumerate(unmatched_target):
            if source_unit == target_unit and _numeric_equivalent(source_number, target_number):
                match_index = index
                break
        if match_index is None:
            missing.append("{} {}".format(source_number, source_unit))
        else:
            unmatched_target.pop(match_index)
    extra = ["{} {}".format(number, unit) for number, unit in unmatched_target]
    return missing, extra


def _issue(unit, check_id, severity, message, source_items, target_items, glossary_entry_id=None, note=None):
    value = {
        "unit_id": unit["id"],
        "check_id": check_id,
        "classification": "POTENTIAL_ISSUE",
        "severity": severity,
        "message": message,
        "source_items": list(source_items),
        "target_items": list(target_items),
    }
    if unit.get("location"):
        value["location"] = unit["location"]
    if glossary_entry_id:
        value["glossary_entry_id"] = glossary_entry_id
    if note is not None:
        value["note"] = note
    return value


def _check_literal(unit, check_id, severity, source_items, target_items):
    missing, extra = _counter_diff(source_items, target_items)
    if not missing and not extra:
        return None
    return _issue(
        unit, check_id, severity,
        "Source and target do not preserve the same {} items.".format(check_id.lower()),
        missing, extra,
    )


def run_qa(units, config, glossary=None):
    checks = config.get("checks", {})
    unit_allowlist = config.get("unit_allowlist") or []
    issues = []
    checks_run = []

    literal_extractors = [
        ("PLACEHOLDER_INTEGRITY", extract_placeholders),
        ("URL_INTEGRITY", extract_urls),
        ("PATH_INTEGRITY", extract_paths),
        ("FILENAME_INTEGRITY", extract_filenames),
        ("CLI_OPTION_INTEGRITY", extract_cli_options),
        ("ENV_VAR_INTEGRITY", extract_env_vars),
        ("VERSION_INTEGRITY", extract_versions),
    ]

    for check_id, _ in literal_extractors:
        if checks.get(check_id, {}).get("enabled"):
            checks_run.append(check_id)
    for check_id in ("NUMBER_INTEGRITY", "NUMBER_UNIT_INTEGRITY", "PROTECTED_LITERAL", "FORBIDDEN_TERM", "PREFERRED_TERM"):
        if checks.get(check_id, {}).get("enabled"):
            checks_run.append(check_id)

    for unit in units:
        source = unit["source"]
        target = unit["target"]

        for check_id, extractor in literal_extractors:
            rule = checks.get(check_id, {})
            if not rule.get("enabled"):
                continue
            candidate = _check_literal(
                unit, check_id, rule["severity"], extractor(source), extractor(target)
            )
            if candidate:
                issues.append(candidate)

        rule = checks.get("NUMBER_UNIT_INTEGRITY", {})
        if rule.get("enabled"):
            source_items = extract_number_units(source, unit_allowlist)
            target_items = extract_number_units(target, unit_allowlist)
            missing, extra = _number_unit_diff(source_items, target_items)
            if missing or extra:
                issues.append(_issue(
                    unit, "NUMBER_UNIT_INTEGRITY", rule["severity"],
                    "Source and target do not preserve equivalent number-unit pairs.",
                    missing, extra,
                ))

        rule = checks.get("NUMBER_INTEGRITY", {})
        if rule.get("enabled"):
            source_items = extract_plain_numbers(source, unit_allowlist)
            target_items = extract_plain_numbers(target, unit_allowlist)
            missing, extra = _numeric_multiset_diff(source_items, target_items)
            if missing or extra:
                issues.append(_issue(
                    unit, "NUMBER_INTEGRITY", rule["severity"],
                    "Source and target do not preserve equivalent standalone numbers.",
                    missing, extra,
                ))

        for entry in _approved_entries(glossary):
            if not _scope_applies(entry, unit):
                continue
            source_record = entry.get("source") or {}
            source_language = source_record.get("language")
            unit_source_language = unit.get("source_language")
            behavior = entry.get("behavior")
            if behavior != "PROTECT" and source_language:
                if unit_source_language is None or unit_source_language != source_language:
                    continue
            match = entry.get("match") or {}
            mode = match.get("mode", "token")
            case_sensitive = bool(match.get("case_sensitive", False))
            normalization = match.get("unicode_normalization", "NFC")
            source_term = source_record.get("term", "")
            if not source_term or not _contains_term(source, source_term, mode, case_sensitive, normalization):
                continue

            entry_id = entry.get("id") or entry.get("entry_id")
            targets = entry.get("targets") or []

            if behavior == "PROTECT":
                rule = checks.get("PROTECTED_LITERAL", {})
                if rule.get("enabled") and not _contains_term(target, source_term, mode, True, normalization):
                    issues.append(_issue(
                        unit, "PROTECTED_LITERAL", rule["severity"],
                        "A project-approved protected literal from the source is not preserved exactly in the target.",
                        [source_term], [], entry_id,
                    ))
                continue

            if behavior != "TRANSLATE":
                continue

            relevant_targets = []
            target_language = unit.get("target_language")
            if target_language is None:
                continue
            for candidate in targets:
                lang = candidate.get("language")
                if lang and lang != target_language:
                    continue
                relevant_targets.append(candidate)

            forbidden = [x.get("term", "") for x in relevant_targets if x.get("status") == "FORBIDDEN"]
            admitted = [x.get("term", "") for x in relevant_targets if x.get("status") == "ADMITTED"]
            preferred = [x.get("term", "") for x in relevant_targets if x.get("status") == "PREFERRED"]

            rule = checks.get("FORBIDDEN_TERM", {})
            if rule.get("enabled"):
                found = [term for term in forbidden if term and _contains_term(target, term, mode, case_sensitive, normalization)]
                if found:
                    issues.append(_issue(
                        unit, "FORBIDDEN_TERM", rule["severity"],
                        "Target contains a project-approved forbidden designation.",
                        [source_term], found, entry_id,
                    ))

            rule = checks.get("PREFERRED_TERM", {})
            if rule.get("enabled") and preferred:
                accepted = preferred + admitted
                if not any(term and _contains_term(target, term, mode, case_sensitive, normalization) for term in accepted):
                    issues.append(_issue(
                        unit, "PREFERRED_TERM", rule["severity"],
                        "Source concept is present but no preferred or admitted project designation was found in the target.",
                        [source_term], [], entry_id,
                        note="Preferred: {}".format(" | ".join(preferred)),
                    ))

    for index, issue in enumerate(issues, 1):
        issue["id"] = "Q{:04d}".format(index)

    error_count = sum(1 for x in issues if x["severity"] == "ERROR")
    warning_count = sum(1 for x in issues if x["severity"] == "WARNING")
    return {
        "format_version": "1.0",
        "summary": {
            "units_checked": len(units),
            "error_count": error_count,
            "warning_count": warning_count,
        },
        "checks_run": checks_run,
        "issues": issues,
    }


def validate_report(report, schema_path=REPORT_SCHEMA):
    schema = _read_json(schema_path)
    validator = Draft202012Validator(schema)
    return [error.message for error in sorted(validator.iter_errors(report), key=lambda e: list(e.path))]


def _load_glossary(path):
    if path is None:
        return None
    scripts = str((ROOT / "scripts").resolve())
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from glossary_io import load_glossary, validate_glossary
    glossary = load_glossary(path)
    errors = validate_glossary(glossary)
    if errors:
        raise ValueError("invalid glossary:\n" + "\n".join(errors))
    return glossary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("units", help="JSON array/object or JSONL bilingual units")
    parser.add_argument("--glossary", help="Project glossary JSON or CSV")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output", help="Write JSON report to this path")
    args = parser.parse_args()

    try:
        units = load_units(args.units)
        unit_errors = validate_units(units)
        if unit_errors:
            raise ValueError("invalid bilingual units:\n" + "\n".join(unit_errors))
        config = load_config(args.config)
        glossary = _load_glossary(args.glossary)
        report = run_qa(units, config, glossary)
        report["source"] = str(args.units)
        if args.glossary:
            report["glossary"] = str(args.glossary)
        errors = validate_report(report)
        if errors:
            raise ValueError("generated report violates schema:\n" + "\n".join(errors))
    except (OSError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        parser.exit(2, str(exc) + "\n")

    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 1 if report["summary"]["error_count"] else 0


if __name__ == "__main__":
    sys.exit(main())

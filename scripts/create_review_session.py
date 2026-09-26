#!/usr/bin/env python3
"""Create a DBabel .dbreview directory from aligned units and optional DBabel reports."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from review_model import (
    default_decision,
    deterministic_issue_to_review,
    read_json,
    read_jsonl,
    semantic_finding_to_review,
    sha256_file,
    utc_now,
    write_json,
    write_jsonl,
)
from docx_review_adapter import build_anchors
from version_info import REVIEW_WORKBENCH_VERSION
from technique_contract import (
    load_translation_registry,
    validate_technique_annotation,
)


def _load_units(path: Path) -> List[Dict[str, Any]]:
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        raw = read_jsonl(path)
    else:
        value = read_json(path)
        if isinstance(value, dict) and isinstance(value.get("units"), list):
            raw = value["units"]
        elif isinstance(value, list):
            raw = value
        else:
            raise ValueError("units must be a JSON array, {units:[...]}, or JSONL")
    result: List[Dict[str, Any]] = []
    seen = set()
    for index, unit in enumerate(raw, 1):
        if not isinstance(unit, dict):
            raise ValueError("unit {} is not an object".format(index))
        unit_id = str(unit.get("id") or "U{:04d}".format(index))
        if unit_id in seen:
            raise ValueError("duplicate unit id {}".format(unit_id))
        seen.add(unit_id)
        if "source" not in unit or "target" not in unit:
            raise ValueError("unit {} requires source and target".format(unit_id))
        location = str(unit.get("location") or "unit:{}".format(unit_id))
        review = {
            "id": unit_id,
            "location": location,
            "source": str(unit.get("source") or ""),
            "current_target": str(unit.get("target") or ""),
            "labels": [],
            "finding_refs": [],
            "qa_issue_refs": [],
            "evidence_refs": [],
            "requires_confirmation": True,
        }

        for key in ("suggested_target", "suggestion_reason"):
            if isinstance(unit.get(key), str) and unit[key].strip():
                review[key] = unit[key]

        alignment = str(
            unit.get("alignment") or "ALIGNED"
        ).upper()

        allowed_alignments = {
            "ALIGNED",
            "AMBIGUOUS",
            "SPLIT",
            "MERGED",
            "UNALIGNED",
        }

        if alignment not in allowed_alignments:
            raise ValueError(
                "unit {} has unsupported alignment {}".format(
                    unit_id,
                    alignment,
                )
            )

        review["alignment"] = alignment

        if unit.get("alignment_id"):
            review["alignment_id"] = str(
                unit["alignment_id"]
            )

        for refs_key in (
            "source_refs",
            "target_refs",
        ):
            if refs_key not in unit:
                continue

            raw_refs = unit[refs_key]

            if not isinstance(raw_refs, list):
                raise ValueError(
                    "unit {} {} must be an array".format(
                        unit_id,
                        refs_key,
                    )
                )

            refs = [
                str(ref)
                for ref in raw_refs
                if str(ref)
            ]

            if len(refs) != len(raw_refs):
                raise ValueError(
                    "unit {} {} contains an empty reference".format(
                        unit_id,
                        refs_key,
                    )
                )

            if len(refs) != len(set(refs)):
                raise ValueError(
                    "unit {} {} contains duplicate references".format(
                        unit_id,
                        refs_key,
                    )
                )

            review[refs_key] = refs

        for key in ("source_language", "target_language"):
            if unit.get(key):
                review[key] = str(unit[key])
        context = unit.get("context")
        if isinstance(context, dict):
            clean_context = {k: str(v) for k, v in context.items() if k in {"vendor", "product", "version", "domain", "text_role"} and v is not None}
            if clean_context:
                review["context"] = clean_context
                if clean_context.get("text_role"):
                    review["text_role"] = clean_context["text_role"]
        result.append(review)
    return result


def _map_finding_to_unit(finding: Dict[str, Any], units: List[Dict[str, Any]]) -> Optional[str]:
    location = str(finding.get("location") or "")
    exact = [u for u in units if u["location"] == location]
    if len(exact) == 1:
        return exact[0]["id"]
    original = str(finding.get("original") or "")
    if original:
        candidates = [u for u in units if original in u["current_target"] or original in u["source"]]
        if len(candidates) == 1:
            return candidates[0]["id"]
    return None


def _aggregate_suggestion(unit: Dict[str, Any], mapped_findings: List[Dict[str, Any]]) -> Optional[str]:
    current = unit["current_target"]
    proposed = current
    changed = False
    spans = []
    for finding in mapped_findings:
        if finding.get("decision") != "REPLACE" or not finding.get("recommendation"):
            continue
        old = str(finding.get("original") or "")
        new = str(finding["recommendation"])
        if not old or proposed.count(old) != 1:
            continue
        start = proposed.find(old)
        end = start + len(old)
        if any(not (end <= a or start >= b) for a, b in spans):
            continue
        proposed = proposed[:start] + new + proposed[end:]
        spans.append((start, start + len(new)))
        changed = True
    return proposed if changed and proposed != current else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("units", help="Aligned bilingual units JSON/JSONL")
    parser.add_argument("--qa-report", help="Deterministic QA report JSON")
    parser.add_argument("--audit-report", help="DBabel audit report JSON")
    parser.add_argument("--original", help="Original target document used for future native export")
    parser.add_argument("--output", required=True, help="Output directory ending in .dbreview")
    parser.add_argument("--title")
    parser.add_argument("--mode", default="BILINGUAL_REVIEW", choices=["BILINGUAL_REVIEW", "TRANSLATE", "AUDIT", "REPAIR"])
    parser.add_argument("--include-path-hint", action="store_true", help="Store local original path in session.json")
    args = parser.parse_args()

    units_path = Path(args.units).resolve()
    output = Path(args.output).resolve()
    if output.exists():
        parser.error("output already exists: {}".format(output))
    if output.suffix != ".dbreview":
        parser.error("output directory must end in .dbreview")

    try:
        units = _load_units(units_path)
        unit_by_id = {x["id"]: x for x in units}
        issues: List[Dict[str, Any]] = []
        evidence: List[Dict[str, Any]] = []
        findings_by_unit: Dict[str, List[Dict[str, Any]]] = {}

        if args.qa_report:
            qa = read_json(Path(args.qa_report))
            for raw_issue in qa.get("issues") or []:
                converted = deterministic_issue_to_review(raw_issue)
                if converted["unit_id"] not in unit_by_id:
                    raise ValueError("QA issue references unknown unit {}".format(converted["unit_id"]))
                issues.append(converted)
                unit = unit_by_id[converted["unit_id"]]
                unit["qa_issue_refs"].append(converted["id"])
                unit["labels"].append(converted["label"])

        if args.audit_report:
            audit = read_json(
                Path(
                    args.audit_report
                )
            )

            technique_registry = (
                load_translation_registry(
                    HERE.parent
                )
            )

            evidence = list(
                audit.get(
                    "sources"
                )
                or []
            )
            evidence_ids = {str(x.get("id")) for x in evidence}
            for finding in audit.get("findings") or []:
                technique_errors = (
                    validate_technique_annotation(
                        finding.get(
                            "technique"
                        ),
                        technique_registry,
                    )
                )

                if technique_errors:
                    raise ValueError(
                        "finding {} technique: {}".format(
                            finding.get(
                                "id",
                                "<unknown>",
                            ),
                            "; ".join(
                                technique_errors
                            ),
                        )
                    )

                unit_id = _map_finding_to_unit(
                    finding,
                    units,
                )
                if unit_id is None:
                    # Unmappable findings stay visible as limitations outside the unit grid.
                    continue
                converted = semantic_finding_to_review(finding, unit_id)
                issues.append(converted)
                unit = unit_by_id[unit_id]
                unit["finding_refs"].append(converted["id"])
                unit["labels"].extend([converted["label"], converted["classification"]])
                for ref in converted.get("evidence_refs") or []:
                    if ref in evidence_ids:
                        unit["evidence_refs"].append(ref)
                findings_by_unit.setdefault(unit_id, []).append(finding)

        for unit in units:
            suggestion = _aggregate_suggestion(unit, findings_by_unit.get(unit["id"], []))
            if suggestion is not None:
                unit["suggested_target"] = suggestion
            unit["labels"] = sorted(set(unit["labels"]))
            unit["finding_refs"] = sorted(set(unit["finding_refs"]))
            unit["qa_issue_refs"] = sorted(set(unit["qa_issue_refs"]))
            unit["evidence_refs"] = sorted(set(unit["evidence_refs"]))

        if args.original:
            original = Path(args.original).resolve()
            if not original.is_file():
                raise ValueError("original file not found: {}".format(original))
            original_info = {
                "filename": original.name,
                "format": original.suffix.lower().lstrip(".") or "unknown",
                "sha256": sha256_file(original),
            }
            if args.include_path_hint:
                original_info["path_hint"] = str(original)
            if original.suffix.lower() == ".docx":
                anchorable_units = [
                    unit
                    for unit in units
                    if unit.get("alignment", "ALIGNED") == "ALIGNED"
                ]

                anchors = build_anchors(
                    original,
                    anchorable_units,
                )

                for unit in units:
                    if unit.get("alignment", "ALIGNED") == "ALIGNED":
                        continue

                    anchors[unit["id"]] = {
                        "id": "A_{}".format(unit["id"]),
                        "unit_id": unit["id"],
                        "status": "BLOCKED",
                        "reason": (
                            "native DOCX anchor disabled because "
                            "alignment is {}".format(
                                unit["alignment"]
                            )
                        ),
                        "original_text": unit["current_target"],
                    }
            else:
                anchors = {}
        else:
            original = units_path
            original_info = {
                "filename": units_path.name,
                "format": "review-data",
                "sha256": sha256_file(units_path),
            }
            anchors = {}

        output.mkdir(parents=True)
        decisions = [default_decision(unit["id"]) for unit in units]
        session = {
            "format_version": "1.0",
            "session_id": "RS_{}".format(uuid.uuid4().hex),
            "created_at": utc_now(),
            "dbabel_version": REVIEW_WORKBENCH_VERSION,
            "mode": args.mode,
            "title": args.title or ("Review: " + original_info["filename"]),
            "bundle_files": {
                "units": "units.jsonl",
                "issues": "issues.json",
                "evidence": "evidence.json",
                "decisions": "decisions.json",
                "events": "events.jsonl",
                "anchors": "anchors.json"
            },
            "original": original_info,
            "counts": {"units": len(units), "issues": len(issues), "evidence": len(evidence)},
            "export_policy": {
                "require_all_confirmed": True,
                "block_unwaived_errors": True,
                "require_user_edit_recheck": True,
                "never_overwrite_original": True
            }
        }
        if args.audit_report:
            audit = read_json(Path(args.audit_report))
            if audit.get("document"):
                session["source_document"] = str(audit["document"])
        if args.original:
            session["target_document"] = original_info["filename"]

        write_json(output / "session.json", session)
        write_jsonl(output / "units.jsonl", units)
        write_json(output / "issues.json", issues)
        write_json(output / "evidence.json", evidence)
        write_json(output / "decisions.json", decisions)
        write_json(output / "anchors.json", anchors)
        (output / "original.sha256").write_text(original_info["sha256"] + "  " + original_info["filename"] + "\n", encoding="utf-8")
        write_jsonl(output / "events.jsonl", [{
            "event": "SESSION_CREATED",
            "at": utc_now(),
            "revision": 0,
            "actor": "SYSTEM",
            "detail": "Review session created from aligned bilingual units"
        }])
        print(str(output))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(2, str(exc) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())

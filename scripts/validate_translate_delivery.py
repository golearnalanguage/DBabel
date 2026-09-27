#!/usr/bin/env python3
"""Fail-closed delivery gate for DBabel translation-review handoffs.

A successful result means the review package is READY_FOR_HUMAN_REVIEW. It does
not fabricate human approval and never upgrades a pending translation to COMPLETED.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from review_model import load_bundle, validate_bundle, sha256_file
from prepare_review_qa import read_units, cross_language, proposal_decision

PROTECTED = {"KEEP", "PROTECT"}
PROPOSAL_MODES = {"TRANSLATE", "BILINGUAL_REVIEW", "REPAIR"}


def candidate_id(candidate: Dict[str, Any], index: int) -> str:
    return str(
        candidate.get("entry_id")
        or candidate.get("id")
        or "GC{:04d}".format(index)
    )


def candidate_matches(candidate: Dict[str, Any], unit: Dict[str, Any]) -> bool:
    term = str(candidate.get("term") or candidate.get("source_term") or "")
    if not term:
        return False
    haystack = "\n".join(
        str(unit.get(key) or "")
        for key in ("source", "current_target", "suggested_target")
    )
    return term in haystack or term.casefold() in haystack.casefold()


def validate_delivery(
    bundle: Path,
    repo_root: Path,
    qa_input: Optional[Path],
    qa_report: Optional[Path],
    audit_report: Optional[Path],
    surface: str,
    allow_portable_fallback: bool,
) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []

    errors.extend(validate_bundle(bundle, repo_root))
    data = load_bundle(bundle)
    session = data["session"]
    mode = str(session.get("mode") or "")

    if mode not in PROPOSAL_MODES:
        errors.append(
            "delivery gate requires TRANSLATE/BILINGUAL_REVIEW/REPAIR session"
        )

    for unit in data["units"]:
        if (
            unit.get("proposal_decision") == "REPLACE"
            and not str(unit.get("suggested_target") or "").strip()
        ):
            errors.append("{} REPLACE has no suggested_target".format(unit["id"]))

    if mode in {"TRANSLATE", "BILINGUAL_REVIEW"}:
        preparation = session.get("preparation") or {}

        if not preparation.get("qa_report_bound"):
            errors.append(
                "review session was not created with --qa-report"
            )
        if not preparation.get("audit_report_bound"):
            errors.append(
                "review session was not created with --audit-report"
            )

        if qa_report is None:
            errors.append("the bound deterministic QA report is required")
        else:
            expected_qa = preparation.get("qa_report_sha256")
            actual_qa = sha256_file(qa_report)
            if expected_qa and actual_qa != expected_qa:
                errors.append(
                    "QA report hash does not match the report bound to the session"
                )

        if audit_report is None:
            errors.append("the bound audit report is required")
        else:
            expected_audit = preparation.get("audit_report_sha256")
            actual_audit = sha256_file(audit_report)
            if expected_audit and actual_audit != expected_audit:
                errors.append(
                    "audit report hash does not match the report bound to the session"
                )

        if qa_input is None:
            errors.append("cross-language proposal QA input is required")
        else:
            qa_units = read_units(qa_input)
            review_by_id = data["units_by_id"]
            for qa in qa_units:
                review = review_by_id.get(str(qa.get("id")))
                if review is None:
                    errors.append(
                        "QA input references unknown unit {}".format(qa.get("id"))
                    )
                    continue
                if (
                    cross_language(qa)
                    and str(qa.get("source") or "") == str(qa.get("target") or "")
                    and proposal_decision(review) not in PROTECTED
                ):
                    errors.append(
                        "{} QA target is identical to source without KEEP/PROTECT".format(
                            qa.get("id")
                        )
                    )

    if audit_report is not None:
        audit = json.loads(audit_report.read_text(encoding="utf-8"))
        candidates = audit.get("glossary_candidates") or []

        for index, candidate in enumerate(candidates, 1):
            if not isinstance(candidate, dict):
                continue
            cid = candidate_id(candidate, index)
            matched = [
                unit
                for unit in data["units"]
                if candidate_matches(candidate, unit)
            ]
            if matched and not any(
                cid in (unit.get("term_refs") or [])
                for unit in matched
            ):
                errors.append(
                    "glossary candidate {} matches review text but is not bound "
                    "to a review unit".format(cid)
                )

        referenced_evidence = set()
        for finding in audit.get("findings") or []:
            if isinstance(finding, dict):
                referenced_evidence.update(
                    str(ref) for ref in finding.get("evidence_refs") or []
                )
        for candidate in candidates:
            if isinstance(candidate, dict):
                referenced_evidence.update(
                    str(ref) for ref in candidate.get("evidence_refs") or []
                )

        if referenced_evidence:
            session_evidence = {
                str(item.get("id"))
                for item in data["evidence"]
                if isinstance(item, dict)
            }
            missing = referenced_evidence - session_evidence
            if missing:
                errors.append(
                    "referenced evidence missing from review session: "
                    + ", ".join(sorted(missing))
                )

            bound = {
                ref
                for unit in data["units"]
                for ref in (unit.get("evidence_refs") or [])
            }
            if not (referenced_evidence & bound):
                errors.append(
                    "audit used evidence but no review unit is linked to that evidence"
                )

    if surface == "full":
        required = [
            repo_root / "scripts" / "start_review_workbench.py",
            repo_root / "review_workbench" / "static" / "exchange.js",
            repo_root / "review_workbench" / "static" / "workbench_views.js",
        ]
        for path in required:
            if not path.is_file():
                errors.append(
                    "full local Workbench capability missing: {}".format(path)
                )
        surface_status = "FULL_LOCAL_WORKBENCH_READY"
    else:
        surface_status = "PORTABLE_FALLBACK_ONLY"
        if not allow_portable_fallback:
            errors.append(
                "Portable Review is a fallback decision surface, not the Full "
                "Local Review Workbench"
            )
        else:
            warnings.append(
                "Portable Review accepted only as fallback; glossary upload, fresh "
                "local QA and native export require the Full Local Workbench."
            )

    if session.get("original", {}).get("format") == "xlsx":
        if not (repo_root / "scripts" / "xlsx_review_adapter.py").is_file():
            errors.append("XLSX session requires xlsx_review_adapter.py")
        for unit in data["units"]:
            if unit.get("proposal_decision") != "REPLACE":
                continue
            anchor = data["anchors"].get(unit["id"]) or {}
            if anchor.get("status") != "RESOLVED":
                errors.append(
                    "{} XLSX REPLACE lacks a resolved cell anchor".format(
                        unit["id"]
                    )
                )

    status = (
        "BLOCKED"
        if errors
        else (
            "READY_WITH_PORTABLE_FALLBACK"
            if surface == "portable"
            else "READY_FOR_HUMAN_REVIEW"
        )
    )

    return {
        "format_version": "1.0",
        "status": status,
        "workflow_stage": status,
        "completion_allowed": False,
        "surface": surface_status,
        "session_id": session.get("session_id"),
        "mode": mode,
        "counts": {
            "units": len(data["units"]),
            "issues": len(data["issues"]),
            "evidence": len(data["evidence"]),
            "term_bound_units": sum(
                1 for unit in data["units"] if unit.get("term_refs")
            ),
            "suggested_units": sum(
                1 for unit in data["units"] if unit.get("suggested_target")
            ),
        },
        "errors": errors,
        "warnings": warnings,
        "next_action": (
            "Resolve delivery-gate errors before claiming the review is ready."
            if errors
            else "Open the Full Local Review Workbench and collect human decisions."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", help=".dbreview directory")
    parser.add_argument("--repo-root", default=str(HERE.parent))
    parser.add_argument(
        "--qa-input",
        help="Prepared source↔proposal QA input from prepare_review_qa.py",
    )
    parser.add_argument(
        "--qa-report",
        help="Deterministic QA report bound when creating the session",
    )
    parser.add_argument("--audit-report")
    parser.add_argument(
        "--surface",
        choices=["full", "portable"],
        default="full",
    )
    parser.add_argument("--allow-portable-fallback", action="store_true")
    parser.add_argument("--output", help="Write delivery receipt JSON")
    args = parser.parse_args()

    try:
        receipt = validate_delivery(
            Path(args.bundle).resolve(),
            Path(args.repo_root).resolve(),
            Path(args.qa_input).resolve() if args.qa_input else None,
            Path(args.qa_report).resolve() if args.qa_report else None,
            Path(args.audit_report).resolve() if args.audit_report else None,
            args.surface,
            args.allow_portable_fallback,
        )
        text = json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            Path(args.output).write_text(text, encoding="utf-8")
        print(text, end="")
        return 0 if receipt["status"] != "BLOCKED" else 1
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(2, str(exc) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())

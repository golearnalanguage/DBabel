#!/usr/bin/env python3
"""Prepare DBabel deterministic-QA input from the text actually under review.

For TRANSLATE/BILINGUAL_REVIEW, QA compares source with approved_target when
present, otherwise suggested_target. A source-language current target is an anchor,
not a translation. Explicit KEEP/PROTECT units may remain identical by design.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

PROTECTED_DECISIONS = {"KEEP", "PROTECT"}


def read_units(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    stripped = text.lstrip()
    if not stripped:
        return []
    if stripped.startswith("["):
        value = json.loads(text)
        if not isinstance(value, list):
            raise ValueError("JSON root must be an array")
        return value
    if stripped.startswith("{"):
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            value = None
        if isinstance(value, dict) and isinstance(value.get("units"), list):
            return value["units"]
        if isinstance(value, dict):
            return [value]
    units = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError("{}:{}: unit must be an object".format(path, lineno))
        units.append(value)
    return units


def proposal_decision(unit: Dict[str, Any]) -> str:
    raw = unit.get("proposal_decision", unit.get("_decision", unit.get("decision", "")))
    if isinstance(raw, dict):
        raw = raw.get("decision") or raw.get("status") or ""
    return str(raw or "").upper()


def cross_language(unit: Dict[str, Any]) -> bool:
    source = str(unit.get("source_language") or "").strip().casefold()
    target = str(unit.get("target_language") or "").strip().casefold()
    return bool(source and target and source != target)


def target_for(unit: Dict[str, Any]) -> Tuple[str, str]:
    approved = unit.get("approved_target")
    if isinstance(approved, str) and approved.strip():
        return approved, "approved_target"

    suggested = unit.get("suggested_target")
    if isinstance(suggested, str) and suggested.strip():
        return suggested, "suggested_target"

    current = str(unit.get("target", unit.get("current_target", "")) or "")
    source = str(unit.get("source") or "")
    decision = proposal_decision(unit)

    if decision in PROTECTED_DECISIONS:
        return current, "protected_current_target"
    if current and current != source:
        return current, "existing_target"

    raise ValueError(
        "unit {} has no reviewable target: provide suggested_target/approved_target; "
        "a source anchor cannot stand in for a translation".format(
            unit.get("id", "<unknown>")
        )
    )


def prepare_units(units: List[Dict[str, Any]], mode: str):
    prepared = []
    selections = []
    identity_cross_language = []

    for index, unit in enumerate(units, 1):
        if not isinstance(unit, dict):
            raise ValueError("unit {} is not an object".format(index))
        if "source" not in unit:
            raise ValueError("unit {} requires source".format(unit.get("id", index)))

        target, selected_from = target_for(unit)
        source = str(unit.get("source") or "")
        decision = proposal_decision(unit)

        if (
            mode in {"TRANSLATE", "BILINGUAL_REVIEW"}
            and cross_language(unit)
            and target == source
            and decision not in PROTECTED_DECISIONS
        ):
            identity_cross_language.append(str(unit.get("id") or index))

        out = {
            "id": str(unit.get("id") or "U{:04d}".format(index)),
            "source": source,
            "target": target,
        }
        for key in (
            "location",
            "source_language",
            "target_language",
            "alignment",
            "context",
        ):
            if key in unit:
                out[key] = unit[key]

        prepared.append(out)
        selections.append(
            {
                "unit_id": out["id"],
                "selected_from": selected_from,
                "proposal_decision": decision or None,
                "identity": source == target,
            }
        )

    if identity_cross_language:
        raise ValueError(
            "cross-language QA would compare source with identical target for: {}. "
            "Use suggested_target/approved_target, or explicitly classify the unit "
            "KEEP/PROTECT.".format(", ".join(identity_cross_language))
        )

    return prepared, {
        "format_version": "1.0",
        "mode": mode,
        "unit_count": len(prepared),
        "selection": selections,
        "identity_count": sum(1 for item in selections if item["identity"]),
        "identity_policy": (
            "Identity is allowed only for explicit KEEP/PROTECT or same-language "
            "review; it is never accepted as a cross-language translation substitute."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("units", help="Aligned review units JSON/JSONL")
    parser.add_argument(
        "--mode",
        choices=["TRANSLATE", "BILINGUAL_REVIEW", "REPAIR"],
        default="TRANSLATE",
    )
    parser.add_argument("--output", required=True, help="Prepared bilingual QA JSONL")
    parser.add_argument("--receipt", help="Optional QA-target selection receipt JSON")
    args = parser.parse_args()

    try:
        prepared, receipt = prepare_units(read_units(Path(args.units)), args.mode)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8", newline="\n") as handle:
            for unit in prepared:
                handle.write(json.dumps(unit, ensure_ascii=False, sort_keys=True) + "\n")

        if args.receipt:
            Path(args.receipt).write_text(
                json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        print(str(output))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(2, str(exc) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())

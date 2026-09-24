#!/usr/bin/env python3
"""Build a bounded translation-review intake from aligned bilingual units.

This orchestration composes existing DBabel surface extraction, technique
candidate routing, and deterministic QA. It does not create semantic findings,
authorize repair, or represent human approval.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from check_bilingual_integrity import (
    load_config,
    load_units,
    run_qa,
    validate_report as validate_qa_report,
    validate_units,
)
from extract_translation_signals import (
    extract_signal_observations,
    load_surface_rules,
)
from glossary_io import load_glossary
from review_model import validate_against_schema
from suggest_translation_techniques import (
    route_candidates,
)


ROOT = Path(__file__).resolve().parents[1]
INTAKE_SCHEMA = (
    ROOT
    / "schemas"
    / "translation_review_intake.schema.json"
)


class TranslationReviewIntakeError(
    ValueError
):
    pass


def validate_translation_review_intake(
    value: Dict[str, Any],
) -> List[str]:
    return validate_against_schema(
        value,
        INTAKE_SCHEMA,
    )


def determine_phase(
    units: List[Dict[str, Any]],
    mode: str,
) -> str:
    if not units:
        raise TranslationReviewIntakeError(
            "translation review intake requires at least one unit"
        )

    populated = [
        bool(
            str(
                unit.get(
                    "target"
                )
                or ""
            ).strip()
        )
        for unit in units
    ]

    if mode == "BILINGUAL_REVIEW":
        if not all(
            populated
        ):
            raise TranslationReviewIntakeError(
                "BILINGUAL_REVIEW requires non-empty target text for every unit"
            )

        return "BILINGUAL_REVIEW"

    if mode != "TRANSLATE":
        raise TranslationReviewIntakeError(
            "unsupported intake mode: {}".format(
                mode
            )
        )

    if not any(
        populated
    ):
        return "PRE_TRANSLATION"

    if all(
        populated
    ):
        return "POST_TRANSLATION"

    raise TranslationReviewIntakeError(
        "TRANSLATE intake has mixed target readiness; "
        "all targets must be empty or all targets must be populated"
    )


def _unique(
    values: List[str],
) -> List[str]:
    seen = set()
    result = []

    for value in values:
        if value in seen:
            continue

        seen.add(
            value
        )

        result.append(
            value
        )

    return result


def _signals_for_side(
    details: List[Dict[str, Any]],
    side: str,
) -> List[str]:
    return _unique(
        [
            detail[
                "signal"
            ]
            for detail in details
            if detail.get(
                "side"
            )
            == side
        ]
    )


def contrast_from_details(
    unit_id: str,
    details: List[Dict[str, Any]],
) -> Dict[str, Any]:
    source = _signals_for_side(
        details,
        "SOURCE",
    )

    target = _signals_for_side(
        details,
        "TARGET",
    )

    context = _signals_for_side(
        details,
        "CONTEXT",
    )

    target_set = set(
        target
    )

    source_set = set(
        source
    )

    return {
        "unit_id": unit_id,
        "source_signals": source,
        "target_signals": target,
        "context_signals": context,
        "shared": [
            signal
            for signal in source
            if signal in target_set
        ],
        "source_only": [
            signal
            for signal in source
            if signal not in target_set
        ],
        "target_only": [
            signal
            for signal in target
            if signal not in source_set
        ],
    }


def build_signal_contrasts(
    units: List[Dict[str, Any]],
    observations: Dict[str, Any],
) -> List[Dict[str, Any]]:
    observation_by_unit = {
        item[
            "unit_id"
        ]: item
        for item in observations.get(
            "observations",
            [],
        )
    }

    result = []

    for unit in units:
        observation = (
            observation_by_unit.get(
                unit[
                    "id"
                ]
            )
            or {}
        )

        result.append(
            contrast_from_details(
                unit[
                    "id"
                ],
                observation.get(
                    "signal_details",
                    [],
                ),
            )
        )

    return result


def intake_cross_errors(
    value: Dict[str, Any],
) -> List[str]:
    errors: List[str] = []

    mode = value.get(
        "mode"
    )

    phase = value.get(
        "phase"
    )

    units = value.get(
        "units"
    ) or []

    unit_ids = [
        unit.get(
            "id"
        )
        for unit in units
    ]

    if len(
        unit_ids
    ) != len(
        set(
            unit_ids
        )
    ):
        errors.append(
            "duplicate intake unit id"
        )

    unit_id_set = set(
        unit_ids
    )

    surface = value.get(
        "surface_observations"
    ) or {}

    candidates = value.get(
        "technique_candidates"
    ) or {}

    if surface.get(
        "mode"
    ) != mode:
        errors.append(
            "surface observation mode drift"
        )

    if candidates.get(
        "mode"
    ) != mode:
        errors.append(
            "technique candidate mode drift"
        )

    observation_ids = [
        item.get(
            "unit_id"
        )
        for item in surface.get(
            "observations",
            [],
        )
    ]

    candidate_ids = [
        item.get(
            "unit_id"
        )
        for item in candidates.get(
            "units",
            [],
        )
    ]

    if not set(
        observation_ids
    ).issubset(
        unit_id_set
    ):
        errors.append(
            "surface observation references unknown unit"
        )

    if candidate_ids != observation_ids:
        errors.append(
            "technique candidate unit sequence drift"
        )

    contrast_items = value.get(
        "signal_contrasts"
    ) or []

    contrast_ids = [
        item.get(
            "unit_id"
        )
        for item in contrast_items
    ]

    if contrast_ids != unit_ids:
        errors.append(
            "signal contrast unit sequence drift"
        )

    observation_by_unit = {
        item.get(
            "unit_id"
        ): item
        for item in surface.get(
            "observations",
            [],
        )
    }

    for contrast in contrast_items:
        unit_id = contrast.get(
            "unit_id"
        )

        observation = (
            observation_by_unit.get(
                unit_id
            )
            or {}
        )

        expected = (
            contrast_from_details(
                unit_id,
                observation.get(
                    "signal_details",
                    [],
                ),
            )
        )

        if contrast != expected:
            errors.append(
                "{}: signal contrast drift".format(
                    unit_id
                )
            )

    qa = value.get(
        "deterministic_qa"
    ) or {}

    qa_status = qa.get(
        "status"
    )

    report = qa.get(
        "report"
    )

    if phase == "PRE_TRANSLATION":
        if qa_status != "NOT_RUN":
            errors.append(
                "PRE_TRANSLATION must not run deterministic QA"
            )

        if report is not None:
            errors.append(
                "PRE_TRANSLATION deterministic QA report must be null"
            )

    elif phase in {
        "BILINGUAL_REVIEW",
        "POST_TRANSLATION",
    }:
        if qa_status != "RUN":
            errors.append(
                "{} must run deterministic QA".format(
                    phase
                )
            )

        if not isinstance(
            report,
            dict,
        ):
            errors.append(
                "{} requires deterministic QA report".format(
                    phase
                )
            )

        else:
            for issue in report.get(
                "issues",
                [],
            ):
                if issue.get(
                    "unit_id"
                ) not in unit_id_set:
                    errors.append(
                        "deterministic QA references unknown unit {}".format(
                            issue.get(
                                "unit_id"
                            )
                        )
                    )

                if issue.get(
                    "classification"
                ) != "POTENTIAL_ISSUE":
                    errors.append(
                        "deterministic QA issue escaped POTENTIAL_ISSUE boundary"
                    )

    handoff = value.get(
        "handoff"
    ) or {}

    if phase == "PRE_TRANSLATION":
        if (
            handoff.get(
                "status"
            )
            != "READY_FOR_TRANSLATION"
            or handoff.get(
                "next_state"
            )
            != "TRANSLATION"
        ):
            errors.append(
                "PRE_TRANSLATION handoff drift"
            )

    else:
        if (
            handoff.get(
                "status"
            )
            != "READY_FOR_SEMANTIC_ADJUDICATION"
            or handoff.get(
                "next_state"
            )
            != "ADJUDICATION"
        ):
            errors.append(
                "semantic handoff drift"
            )

    return errors


def build_translation_review_intake(
    units: List[Dict[str, Any]],
    mode: str,
    *,
    glossary: Optional[
        Dict[str, Any]
    ] = None,
    source_language: Optional[
        str
    ] = None,
    target_language: Optional[
        str
    ] = None,
    default_text_role: Optional[
        str
    ] = None,
) -> Dict[str, Any]:
    unit_errors = validate_units(
        units
    )

    if unit_errors:
        raise TranslationReviewIntakeError(
            "invalid bilingual units: "
            + "; ".join(
                unit_errors
            )
        )

    phase = determine_phase(
        units,
        mode,
    )

    surface = (
        extract_signal_observations(
            units,
            mode,
            rules=load_surface_rules(),
            source_language=source_language,
            target_language=target_language,
            default_text_role=default_text_role,
        )
    )

    candidates = route_candidates(
        surface
    )

    contrasts = (
        build_signal_contrasts(
            units,
            surface,
        )
    )

    if phase == "PRE_TRANSLATION":
        deterministic_qa = {
            "status": "NOT_RUN",
            "reason": (
                "Target text is not yet available; "
                "deterministic bilingual QA is deferred until post-translation."
            ),
            "report": None,
        }

        handoff = {
            "status": "READY_FOR_TRANSLATION",
            "next_state": "TRANSLATION",
            "reason": (
                "Source-side surface cues and technique candidates are ready "
                "to constrain translation generation."
            ),
        }

    else:
        qa_report = run_qa(
            units,
            load_config(),
            glossary,
        )

        qa_errors = (
            validate_qa_report(
                qa_report
            )
        )

        if qa_errors:
            raise TranslationReviewIntakeError(
                "generated deterministic QA report is invalid: "
                + "; ".join(
                    qa_errors
                )
            )

        deterministic_qa = {
            "status": "RUN",
            "reason": (
                "Aligned source and target text are available for "
                "deterministic bilingual integrity checks."
            ),
            "report": qa_report,
        }

        handoff = {
            "status": (
                "READY_FOR_SEMANTIC_ADJUDICATION"
            ),
            "next_state": "ADJUDICATION",
            "reason": (
                "Surface observations, technique candidates, signal contrasts, "
                "and deterministic QA are ready for semantic review."
            ),
        }

    result = {
        "format_version": "1.0",
        "mode": mode,
        "phase": phase,
        "policy": {
            "surface_signals_are_evidence": False,
            "surface_signals_are_findings": False,
            "technique_candidates_are_findings": False,
            "deterministic_qa_is_semantic_verdict": False,
            "intake_authorizes_repair": False,
            "intake_is_human_approval": False,
        },
        "units": units,
        "surface_observations": surface,
        "technique_candidates": candidates,
        "deterministic_qa": deterministic_qa,
        "signal_contrasts": contrasts,
        "handoff": handoff,
    }

    schema_errors = (
        validate_translation_review_intake(
            result
        )
    )

    if schema_errors:
        raise TranslationReviewIntakeError(
            "generated intake violates schema: "
            + "; ".join(
                schema_errors
            )
        )

    cross_errors = (
        intake_cross_errors(
            result
        )
    )

    if cross_errors:
        raise TranslationReviewIntakeError(
            "generated intake violates cross-contract: "
            + "; ".join(
                cross_errors
            )
        )

    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "units",
        type=Path,
    )

    parser.add_argument(
        "--mode",
        required=True,
        choices=[
            "BILINGUAL_REVIEW",
            "TRANSLATE",
        ],
    )

    parser.add_argument(
        "--glossary",
        type=Path,
    )

    parser.add_argument(
        "--source-language"
    )

    parser.add_argument(
        "--target-language"
    )

    parser.add_argument(
        "--default-text-role"
    )

    parser.add_argument(
        "--output",
        type=Path,
    )

    args = parser.parse_args()

    try:
        units = load_units(
            args.units
        )

        glossary = (
            load_glossary(
                args.glossary
            )
            if args.glossary
            else None
        )

        result = (
            build_translation_review_intake(
                units,
                args.mode,
                glossary=glossary,
                source_language=(
                    args.source_language
                ),
                target_language=(
                    args.target_language
                ),
                default_text_role=(
                    args.default_text_role
                ),
            )
        )

    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        parser.exit(
            2,
            "Translation review intake failed: {}\n".format(
                exc
            ),
        )

    rendered = json.dumps(
        result,
        ensure_ascii=False,
        indent=2,
    ) + "\n"

    if args.output:
        args.output.write_text(
            rendered,
            encoding="utf-8",
        )
    else:
        print(
            rendered,
            end="",
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )

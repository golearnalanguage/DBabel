#!/usr/bin/env python3
"""Route explicit observed signals to candidate translation techniques."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from review_model import validate_against_schema
from technique_contract import load_translation_registry


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"


class TechniqueRoutingError(ValueError):
    pass


def read_json(path: Path) -> Any:
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def validate_signal_observations(
    value: Dict[str, Any],
) -> List[str]:
    return validate_against_schema(
        value,
        SCHEMAS
        / "technique_signal_observations.schema.json",
    )


def validate_candidate_report_schema(
    value: Dict[str, Any],
) -> List[str]:
    return validate_against_schema(
        value,
        SCHEMAS
        / "technique_candidate_report.schema.json",
    )


def known_text_roles(
    registry: Dict[str, Any],
) -> set:
    roles = set()

    for technique in (
        registry.get("techniques")
        or []
    ):
        roles.update(
            technique.get(
                "text_roles",
                [],
            )
        )

    roles.discard("ANY")
    return roles


def candidate_report_cross_errors(
    report: Dict[str, Any],
    registry: Dict[str, Any],
) -> List[str]:
    errors: List[str] = []

    if (
        report.get("registry_version")
        != str(
            registry.get("version")
            or ""
        )
    ):
        errors.append(
            "registry version drift"
        )

    catalog = {
        item["id"]: item
        for item in (
            registry.get("techniques")
            or []
        )
        if isinstance(item, dict)
        and item.get("id")
    }

    for unit in report.get(
        "units",
        [],
    ):
        unit_id = unit.get(
            "unit_id"
        )

        role = unit.get(
            "text_role"
        )

        observed = set(
            unit.get(
                "observed_signals",
                [],
            )
        )

        unmatched = set(
            unit.get(
                "unmatched_signals",
                [],
            )
        )

        candidate_ids = []
        matched_union = set()

        for candidate in unit.get(
            "candidates",
            [],
        ):
            technique_id = candidate.get(
                "technique_id"
            )

            candidate_ids.append(
                technique_id
            )

            technique = catalog.get(
                technique_id
            )

            if technique is None:
                errors.append(
                    "{}: unknown technique {}".format(
                        unit_id,
                        technique_id,
                    )
                )
                continue

            if report.get(
                "mode"
            ) not in set(
                technique.get(
                    "applies_to_modes",
                    [],
                )
            ):
                errors.append(
                    "{} / {}: mode mismatch".format(
                        unit_id,
                        technique_id,
                    )
                )

            roles = set(
                technique.get(
                    "text_roles",
                    [],
                )
            )

            if (
                "ANY" not in roles
                and role not in roles
            ):
                errors.append(
                    "{} / {}: text role mismatch".format(
                        unit_id,
                        technique_id,
                    )
                )

            if (
                candidate.get("category")
                != technique.get("category")
            ):
                errors.append(
                    "{} / {}: category drift".format(
                        unit_id,
                        technique_id,
                    )
                )

            if (
                candidate.get("risk")
                != technique.get("risk")
            ):
                errors.append(
                    "{} / {}: risk drift".format(
                        unit_id,
                        technique_id,
                    )
                )

            expected_dimensions = list(
                (
                    technique.get(
                        "qa_mapping"
                    )
                    or {}
                ).get(
                    "semantic_dimensions",
                    [],
                )
            )

            if (
                candidate.get(
                    "quality_dimensions"
                )
                != expected_dimensions
            ):
                errors.append(
                    "{} / {}: quality dimension drift".format(
                        unit_id,
                        technique_id,
                    )
                )

            if (
                candidate.get(
                    "on_uncertainty"
                )
                != technique.get(
                    "on_uncertainty"
                )
            ):
                errors.append(
                    "{} / {}: uncertainty policy drift".format(
                        unit_id,
                        technique_id,
                    )
                )

            matched = set(
                candidate.get(
                    "matched_triggers",
                    [],
                )
            )

            declared = set(
                technique.get(
                    "triggers",
                    [],
                )
            )

            if not matched:
                errors.append(
                    "{} / {}: no matched trigger".format(
                        unit_id,
                        technique_id,
                    )
                )

            if matched - declared:
                errors.append(
                    "{} / {}: undeclared matched trigger".format(
                        unit_id,
                        technique_id,
                    )
                )

            if matched - observed:
                errors.append(
                    "{} / {}: unobserved matched trigger".format(
                        unit_id,
                        technique_id,
                    )
                )

            matched_union.update(
                matched
            )

        if len(
            candidate_ids
        ) != len(
            set(candidate_ids)
        ):
            errors.append(
                "{}: duplicate candidate technique".format(
                    unit_id
                )
            )

        if unmatched - observed:
            errors.append(
                "{}: unmatched signal was not observed".format(
                    unit_id
                )
            )

        if matched_union & unmatched:
            errors.append(
                "{}: matched and unmatched signals overlap".format(
                    unit_id
                )
            )

        if (
            matched_union
            | unmatched
        ) != observed:
            errors.append(
                "{}: signal coverage mismatch".format(
                    unit_id
                )
            )

    return errors


def route_candidates(
    observations: Dict[str, Any],
    registry: Optional[
        Dict[str, Any]
    ] = None,
) -> Dict[str, Any]:
    input_errors = (
        validate_signal_observations(
            observations
        )
    )

    if input_errors:
        raise TechniqueRoutingError(
            "invalid signal observations: "
            + "; ".join(
                input_errors
            )
        )

    registry = (
        registry
        or load_translation_registry(
            ROOT
        )
    )

    mode = observations[
        "mode"
    ]

    roles = known_text_roles(
        registry
    )

    seen_units = set()
    routed_units = []

    for observation in observations[
        "observations"
    ]:
        unit_id = observation[
            "unit_id"
        ]

        if unit_id in seen_units:
            raise TechniqueRoutingError(
                "duplicate unit_id: {}".format(
                    unit_id
                )
            )

        seen_units.add(
            unit_id
        )

        role = observation[
            "text_role"
        ]

        if role == "ANY":
            raise TechniqueRoutingError(
                "{}: ANY is a catalog wildcard, "
                "not a concrete text role".format(
                    unit_id
                )
            )

        if role not in roles:
            raise TechniqueRoutingError(
                "{}: unknown text role {}".format(
                    unit_id,
                    role,
                )
            )

        signals = list(
            observation[
                "observed_signals"
            ]
        )

        for signal in signals:
            if signal != signal.strip():
                raise TechniqueRoutingError(
                    "{}: non-canonical signal whitespace: {!r}".format(
                        unit_id,
                        signal,
                    )
                )

        candidates = []
        matched_signals = set()

        for technique in (
            registry.get(
                "techniques"
            )
            or []
        ):
            if mode not in set(
                technique.get(
                    "applies_to_modes",
                    [],
                )
            ):
                continue

            technique_roles = set(
                technique.get(
                    "text_roles",
                    [],
                )
            )

            if (
                "ANY" not in technique_roles
                and role
                not in technique_roles
            ):
                continue

            declared = set(
                technique.get(
                    "triggers",
                    [],
                )
            )

            matched = [
                signal
                for signal in signals
                if signal in declared
            ]

            if not matched:
                continue

            matched_signals.update(
                matched
            )

            candidates.append(
                {
                    "technique_id": (
                        technique["id"]
                    ),
                    "category": (
                        technique["category"]
                    ),
                    "risk": (
                        technique["risk"]
                    ),
                    "matched_triggers": (
                        matched
                    ),
                    "quality_dimensions": list(
                        (
                            technique.get(
                                "qa_mapping"
                            )
                            or {}
                        ).get(
                            "semantic_dimensions",
                            [],
                        )
                    ),
                    "on_uncertainty": (
                        technique[
                            "on_uncertainty"
                        ]
                    ),
                }
            )

        routed_units.append(
            {
                "unit_id": unit_id,
                "text_role": role,
                "observed_signals": signals,
                "candidates": candidates,
                "unmatched_signals": [
                    signal
                    for signal in signals
                    if signal
                    not in matched_signals
                ],
            }
        )

    report = {
        "format_version": "1.0",
        "registry_version": str(
            registry.get(
                "version"
            )
            or ""
        ),
        "mode": mode,
        "policy": {
            "observations_are_evidence": False,
            "candidates_are_findings": False,
            "candidates_are_decisions": False,
            "candidates_authorize_repair": False,
            "candidates_are_human_approval": False,
        },
        "units": routed_units,
    }

    schema_errors = (
        validate_candidate_report_schema(
            report
        )
    )

    if schema_errors:
        raise TechniqueRoutingError(
            "generated invalid candidate report: "
            + "; ".join(
                schema_errors
            )
        )

    cross_errors = (
        candidate_report_cross_errors(
            report,
            registry,
        )
    )

    if cross_errors:
        raise TechniqueRoutingError(
            "generated inconsistent candidate report: "
            + "; ".join(
                cross_errors
            )
        )

    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "observations",
        type=Path,
    )

    parser.add_argument(
        "--output",
        type=Path,
    )

    args = parser.parse_args()

    try:
        value = read_json(
            args.observations
        )

        result = route_candidates(
            value
        )

    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        parser.exit(
            2,
            "Technique candidate routing failed: {}\n".format(
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

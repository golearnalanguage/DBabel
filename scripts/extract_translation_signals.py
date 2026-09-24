#!/usr/bin/env python3
"""Extract conservative surface signals from bilingual text units.

The output contains observable routing cues only. It is not evidence, a semantic
finding, a decision, repair authorization, or human approval.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml

from check_bilingual_integrity import (
    extract_env_vars,
    extract_filenames,
    extract_paths,
    extract_placeholders,
    extract_urls,
    extract_versions,
    load_units,
    validate_units,
)
from review_model import validate_against_schema
from suggest_translation_techniques import (
    known_text_roles,
    validate_signal_observations,
)
from technique_contract import (
    load_translation_registry,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RULES = (
    ROOT
    / "config"
    / "surface_signal_rules.yaml"
)
RULE_SCHEMA = (
    ROOT
    / "schemas"
    / "surface_signal_rules.schema.json"
)

SURFACE_SIGNAL_ALLOWLIST = {
    "placeholder",
    "url",
    "path",
    "filename",
    "environment_variable",
    "version_literal",
    "must",
    "must_not",
    "should",
    "required",
    "recommended",
    "all",
    "any",
    "each",
    "both",
    "only",
    "current",
    "selected",
    "either",
    "except",
    "unless",
    "conditional_clause",
    "because",
    "therefore",
    "so_that",
    "ui_text",
    "heading",
}

LITERAL_EXTRACTORS = {
    "placeholders": extract_placeholders,
    "urls": extract_urls,
    "paths": extract_paths,
    "filenames": extract_filenames,
    "environment_variables": extract_env_vars,
    "versions": extract_versions,
}


class SurfaceSignalError(ValueError):
    pass


def load_surface_rules(
    path: Path = DEFAULT_RULES,
) -> Dict[str, Any]:
    value = yaml.safe_load(
        Path(path).read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(
        value,
        dict,
    ):
        raise SurfaceSignalError(
            "surface signal rules must be an object"
        )

    return value


def validate_surface_rules(
    value: Dict[str, Any],
    schema_path: Path = RULE_SCHEMA,
) -> List[str]:
    return validate_against_schema(
        value,
        schema_path,
    )


def surface_rule_cross_errors(
    rules: Dict[str, Any],
    registry: Dict[str, Any],
) -> List[str]:
    errors: List[str] = []

    detector_ids = []
    signals = []

    for group in (
        "literal_detectors",
        "lexical_detectors",
        "context_detectors",
    ):
        for item in (
            rules.get(group)
            or []
        ):
            detector_ids.append(
                item.get("id")
            )

            signals.append(
                item.get("signal")
            )

    if len(
        detector_ids
    ) != len(
        set(detector_ids)
    ):
        errors.append(
            "duplicate surface detector id"
        )

    known_catalog_triggers = {
        trigger
        for technique
        in (
            registry.get(
                "techniques"
            )
            or []
        )
        for trigger
        in (
            technique.get(
                "triggers"
            )
            or []
        )
    }

    unknown_catalog_signals = (
        set(signals)
        - known_catalog_triggers
    )

    if unknown_catalog_signals:
        errors.append(
            "surface rules reference unknown catalog triggers: "
            + ", ".join(
                sorted(
                    unknown_catalog_signals
                )
            )
        )

    unsafe_signals = (
        set(signals)
        - SURFACE_SIGNAL_ALLOWLIST
    )

    if unsafe_signals:
        errors.append(
            "surface rules contain non-allowlisted semantic signals: "
            + ", ".join(
                sorted(
                    unsafe_signals
                )
            )
        )

    unknown_extractors = {
        item.get(
            "extractor"
        )
        for item in (
            rules.get(
                "literal_detectors"
            )
            or []
        )
    } - set(
        LITERAL_EXTRACTORS
    )

    if unknown_extractors:
        errors.append(
            "unsupported literal extractors: "
            + ", ".join(
                sorted(
                    unknown_extractors
                )
            )
        )

    return errors


def _language_base(
    value: Optional[str],
) -> Optional[str]:
    if not value:
        return None

    return re.split(
        r"[-_]",
        value.strip().lower(),
        maxsplit=1,
    )[0]


def _locate_values(
    text: str,
    values: Iterable[str],
) -> List[
    Tuple[
        str,
        int,
        int,
    ]
]:
    cursors: Dict[str, int] = {}
    result = []

    for value in values:
        if not value:
            continue

        start_at = cursors.get(
            value,
            0,
        )

        start = text.find(
            value,
            start_at,
        )

        if start < 0:
            start = text.find(
                value
            )

        if start < 0:
            continue

        end = (
            start
            + len(value)
        )

        cursors[value] = end

        result.append(
            (
                value,
                start,
                end,
            )
        )

    return result


def _token_matches(
    text: str,
    value: str,
) -> Iterable[re.Match]:
    pattern = re.compile(
        r"(?<![A-Za-z0-9_])"
        + re.escape(
            value
        )
        + r"(?![A-Za-z0-9_])",
        re.IGNORECASE,
    )

    return pattern.finditer(
        text
    )


def _substring_matches(
    text: str,
    value: str,
) -> Iterable[
    Tuple[
        int,
        int,
    ]
]:
    start = 0

    while True:
        index = text.find(
            value,
            start,
        )

        if index < 0:
            return

        end = (
            index
            + len(value)
        )

        yield (
            index,
            end,
        )

        start = end


def _append_detail(
    details: List[Dict[str, Any]],
    seen: set,
    signal: str,
    side: str,
    detector_id: str,
    matched_text: str,
    start: Optional[int] = None,
    end: Optional[int] = None,
) -> None:
    key = (
        signal,
        side,
        detector_id,
        matched_text,
        start,
        end,
    )

    if key in seen:
        return

    seen.add(
        key
    )

    detail = {
        "signal": signal,
        "side": side,
        "detector_id": detector_id,
        "matched_text": matched_text,
    }

    if (
        start is not None
        and end is not None
    ):
        detail[
            "start"
        ] = start

        detail[
            "end"
        ] = end

    details.append(
        detail
    )


def _extract_literal_details(
    text: str,
    side: str,
    rules: Dict[str, Any],
    details: List[Dict[str, Any]],
    seen: set,
) -> None:
    for detector in (
        rules.get(
            "literal_detectors"
        )
        or []
    ):
        extractor = (
            LITERAL_EXTRACTORS[
                detector[
                    "extractor"
                ]
            ]
        )

        values = extractor(
            text
        )

        for (
            matched_text,
            start,
            end,
        ) in _locate_values(
            text,
            values,
        ):
            _append_detail(
                details,
                seen,
                detector[
                    "signal"
                ],
                side,
                detector[
                    "id"
                ],
                matched_text,
                start,
                end,
            )


def _extract_lexical_details(
    text: str,
    language: Optional[str],
    side: str,
    rules: Dict[str, Any],
    details: List[Dict[str, Any]],
    seen: set,
) -> None:
    language = _language_base(
        language
    )

    if language is None:
        return

    for detector in (
        rules.get(
            "lexical_detectors"
        )
        or []
    ):
        if language not in {
            _language_base(
                item
            )
            for item in detector[
                "languages"
            ]
        }:
            continue

        for value in detector[
            "values"
        ]:
            if (
                detector[
                    "match"
                ]
                == "TOKEN"
            ):
                for match in _token_matches(
                    text,
                    value,
                ):
                    _append_detail(
                        details,
                        seen,
                        detector[
                            "signal"
                        ],
                        side,
                        detector[
                            "id"
                        ],
                        match.group(
                            0
                        ),
                        match.start(),
                        match.end(),
                    )

            else:
                for (
                    start,
                    end,
                ) in _substring_matches(
                    text,
                    value,
                ):
                    _append_detail(
                        details,
                        seen,
                        detector[
                            "signal"
                        ],
                        side,
                        detector[
                            "id"
                        ],
                        text[
                            start:end
                        ],
                        start,
                        end,
                    )


def _extract_context_details(
    text_role: str,
    rules: Dict[str, Any],
    details: List[Dict[str, Any]],
    seen: set,
) -> None:
    for detector in (
        rules.get(
            "context_detectors"
        )
        or []
    ):
        if (
            detector[
                "field"
            ]
            == "text_role"
            and text_role
            == detector[
                "equals"
            ]
        ):
            _append_detail(
                details,
                seen,
                detector[
                    "signal"
                ],
                "CONTEXT",
                detector[
                    "id"
                ],
                text_role,
            )


def _observation_contract_errors(
    value: Dict[str, Any],
) -> List[str]:
    errors = []

    for observation in value.get(
        "observations",
        [],
    ):
        observed = observation.get(
            "observed_signals",
            [],
        )

        details = observation.get(
            "signal_details",
            [],
        )

        detail_signals = []

        for detail in details:
            signal = detail.get(
                "signal"
            )

            if (
                signal
                not in detail_signals
            ):
                detail_signals.append(
                    signal
                )

            has_start = (
                "start"
                in detail
            )

            has_end = (
                "end"
                in detail
            )

            if (
                has_start
                != has_end
            ):
                errors.append(
                    "{}: detail span is incomplete".format(
                        observation.get(
                            "unit_id"
                        )
                    )
                )

            if (
                has_start
                and detail[
                    "end"
                ]
                < detail[
                    "start"
                ]
            ):
                errors.append(
                    "{}: detail span is reversed".format(
                        observation.get(
                            "unit_id"
                        )
                    )
                )

        if observed != detail_signals:
            errors.append(
                "{}: observed_signals do not match signal_details".format(
                    observation.get(
                        "unit_id"
                    )
                )
            )

    return errors


def extract_signal_observations(
    units: List[Dict[str, Any]],
    mode: str,
    rules: Optional[
        Dict[str, Any]
    ] = None,
    source_language: Optional[str] = None,
    target_language: Optional[str] = None,
    default_text_role: Optional[str] = None,
) -> Dict[str, Any]:
    rules = (
        rules
        or load_surface_rules()
    )

    rule_errors = (
        validate_surface_rules(
            rules
        )
    )

    if rule_errors:
        raise SurfaceSignalError(
            "invalid surface signal rules: "
            + "; ".join(
                rule_errors
            )
        )

    registry = (
        load_translation_registry(
            ROOT
        )
    )

    cross_errors = (
        surface_rule_cross_errors(
            rules,
            registry,
        )
    )

    if cross_errors:
        raise SurfaceSignalError(
            "invalid surface signal cross-contract: "
            + "; ".join(
                cross_errors
            )
        )

    unit_errors = validate_units(
        units
    )

    if unit_errors:
        raise SurfaceSignalError(
            "invalid bilingual units: "
            + "; ".join(
                unit_errors
            )
        )

    valid_roles = (
        known_text_roles(
            registry
        )
    )

    observations = []
    warnings = []

    for unit in units:
        context = (
            unit.get(
                "context"
            )
            or {}
        )

        text_role = (
            context.get(
                "text_role"
            )
            or default_text_role
        )

        if not text_role:
            raise SurfaceSignalError(
                "{}: text role is required for candidate routing".format(
                    unit[
                        "id"
                    ]
                )
            )

        if (
            text_role == "ANY"
            or text_role
            not in valid_roles
        ):
            raise SurfaceSignalError(
                "{}: unsupported concrete text role {}".format(
                    unit[
                        "id"
                    ],
                    text_role,
                )
            )

        details: List[
            Dict[str, Any]
        ] = []

        seen = set()

        source = unit[
            "source"
        ]

        target = unit[
            "target"
        ]

        unit_source_language = (
            unit.get(
                "source_language"
            )
            or source_language
        )

        unit_target_language = (
            unit.get(
                "target_language"
            )
            or target_language
        )

        _extract_literal_details(
            source,
            "SOURCE",
            rules,
            details,
            seen,
        )

        _extract_literal_details(
            target,
            "TARGET",
            rules,
            details,
            seen,
        )

        if (
            source
            and not unit_source_language
        ):
            warnings.append(
                "{}: source language missing; lexical source detectors skipped".format(
                    unit[
                        "id"
                    ]
                )
            )

        if (
            target
            and not unit_target_language
        ):
            warnings.append(
                "{}: target language missing; lexical target detectors skipped".format(
                    unit[
                        "id"
                    ]
                )
            )

        _extract_lexical_details(
            source,
            unit_source_language,
            "SOURCE",
            rules,
            details,
            seen,
        )

        _extract_lexical_details(
            target,
            unit_target_language,
            "TARGET",
            rules,
            details,
            seen,
        )

        _extract_context_details(
            text_role,
            rules,
            details,
            seen,
        )

        if not details:
            continue

        observed_signals = []

        for detail in details:
            signal = detail[
                "signal"
            ]

            if (
                signal
                not in observed_signals
            ):
                observed_signals.append(
                    signal
                )

        observations.append(
            {
                "unit_id": (
                    unit[
                        "id"
                    ]
                ),
                "text_role": (
                    text_role
                ),
                "observed_signals": (
                    observed_signals
                ),
                "signal_details": (
                    details
                ),
            }
        )

    result = {
        "format_version": "1.0",
        "producer": (
            "DETERMINISTIC_SURFACE_V1"
        ),
        "mode": mode,
        "policy": {
            "surface_only": True,
            "semantic_inference_allowed": False,
            "signals_are_evidence": False,
            "signals_are_findings": False,
            "signals_authorize_repair": False,
            "signals_are_human_approval": False,
        },
        "warnings": warnings,
        "observations": observations,
    }

    schema_errors = (
        validate_signal_observations(
            result
        )
    )

    if schema_errors:
        raise SurfaceSignalError(
            "generated invalid signal observation contract: "
            + "; ".join(
                schema_errors
            )
        )

    observation_errors = (
        _observation_contract_errors(
            result
        )
    )

    if observation_errors:
        raise SurfaceSignalError(
            "generated inconsistent signal observations: "
            + "; ".join(
                observation_errors
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
        "--source-language"
    )

    parser.add_argument(
        "--target-language"
    )

    parser.add_argument(
        "--default-text-role"
    )

    parser.add_argument(
        "--rules",
        type=Path,
        default=DEFAULT_RULES,
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

        rules = load_surface_rules(
            args.rules
        )

        result = extract_signal_observations(
            units,
            args.mode,
            rules=rules,
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

    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        yaml.YAMLError,
    ) as exc:
        parser.exit(
            2,
            "Surface signal extraction failed: {}\n".format(
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

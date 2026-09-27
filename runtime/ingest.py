"""Validated document ingest for DBabel TRANSLATE runtime.

This layer converts a supported source document into bounded PRE_TRANSLATION
bilingual units. It reuses DBabel's existing document extractor and ingest
contract. It does not call an AI provider, fabricate target text, perform
semantic adjudication, or imply document-wide coverage beyond the recorded
ingest report.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_translation_review_intake import (  # noqa: E402
    build_translation_review_intake,
    intake_cross_errors,
    validate_translation_review_intake,
)
from check_bilingual_integrity import (  # noqa: E402
    validate_units,
)
from review_exchange import read_document  # noqa: E402
from validate_ingest import (  # noqa: E402
    validate_ingest_report,
)


LANGUAGE_TAG_RE = re.compile(
    r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$"
)

TEXT_FORMATS = {
    "txt",
    "md",
    "markdown",
    "csv",
    "tsv",
    "json",
    "jsonl",
    "html",
}


class RuntimeIngestError(ValueError):
    pass


def _validate_languages(
    source_language: str,
    target_language: str,
) -> None:
    if not LANGUAGE_TAG_RE.fullmatch(source_language or ""):
        raise RuntimeIngestError(
            "invalid source language tag: {!r}".format(
                source_language
            )
        )

    if not LANGUAGE_TAG_RE.fullmatch(target_language or ""):
        raise RuntimeIngestError(
            "invalid target language tag: {!r}".format(
                target_language
            )
        )

    if (
        source_language.casefold()
        == target_language.casefold()
    ):
        raise RuntimeIngestError(
            "TRANSLATE requires different source and target languages"
        )


def _validate_text_role(
    text_role: str,
) -> str:
    role = str(
        text_role or ""
    ).strip()

    if not role:
        raise RuntimeIngestError(
            "a concrete text role is required "
            "before translation candidate routing"
        )

    if role == "ANY":
        raise RuntimeIngestError(
            "ANY is not a concrete text role"
        )

    return role


def _unit_id(
    index: int,
    target_language: str,
) -> str:
    return "U{:05d}_{}".format(
        index,
        target_language,
    )


def build_translation_units(
    source_info: Dict[str, Any],
    source_language: str,
    target_language: str,
    default_text_role: str,
) -> List[Dict[str, Any]]:
    _validate_languages(
        source_language,
        target_language,
    )

    text_role = _validate_text_role(
        default_text_role
    )

    segments = source_info.get("segments")

    if not isinstance(segments, list) or not segments:
        raise RuntimeIngestError(
            "document ingest produced no segments"
        )

    units: List[Dict[str, Any]] = []

    seen_locations = set()

    for index, segment in enumerate(
        segments,
        1,
    ):
        if not isinstance(segment, dict):
            raise RuntimeIngestError(
                "segment {} is not an object".format(index)
            )

        location = str(
            segment.get("location") or ""
        )

        text = str(
            segment.get("text") or ""
        )

        if not location:
            raise RuntimeIngestError(
                "segment {} has no stable location".format(
                    index
                )
            )

        if location in seen_locations:
            raise RuntimeIngestError(
                "duplicate ingest location: {}".format(
                    location
                )
            )

        seen_locations.add(location)

        if not text.strip():
            raise RuntimeIngestError(
                "segment {} is unexpectedly empty".format(
                    index
                )
            )

        units.append({
            "id": _unit_id(
                index,
                target_language,
            ),
            "location": location,
            "source": text,
            "target": "",
            "source_language":
                source_language,
            "target_language":
                target_language,
            "alignment": "ALIGNED",
            "context": {
                "text_role": text_role,
            },
        })

    errors = validate_units(units)

    if errors:
        raise RuntimeIngestError(
            "generated invalid bilingual units: "
            + "; ".join(errors)
        )

    return units


def build_ingest_report(
    source: Path,
    source_info: Dict[str, Any],
    backend: str,
    unit_count: int,
) -> Dict[str, Any]:
    limitations = [
        str(item)
        for item in (
            source_info.get("limitations")
            or []
        )
        if str(item).strip()
    ]

    fmt = str(
        source_info.get("format")
        or "unknown"
    )

    segments = (
        source_info.get("segments")
        or []
    )

    locations_available = bool(
        segments
    ) and all(
        isinstance(item, dict)
        and bool(
            str(
                item.get("location")
                or ""
            )
        )
        for item in segments
    )

    if fmt in TEXT_FORMATS:
        structure = {
            "status": "NOT_APPLICABLE",
            "inspected": [],
            "uninspected": [],
        }

    elif limitations:
        structure = {
            "status": "PARTIAL",
            "inspected": [
                "bounded extractor scope"
            ],
            "uninspected": list(
                limitations
            ),
        }

    else:
        structure = {
            "status": "VERIFIED",
            "inspected": [
                "declared extractor scope"
            ],
            "uninspected": [],
        }

    status = (
        "PARTIAL"
        if limitations
        else "PASS"
    )

    report = {
        "format_version": "1.0",
        "source": str(
            Path(source).resolve()
        ),
        "format": fmt,
        "backend": str(
            backend or "unknown"
        ),
        "status": status,
        "units_extracted": int(
            unit_count
        ),
        "locations_available":
            locations_available,
        "structure": structure,
        "warnings": [],
        "limitations": limitations,
    }

    errors = validate_ingest_report(
        report
    )

    if errors:
        raise RuntimeIngestError(
            "generated invalid ingest report: "
            + "; ".join(errors)
        )

    return report


def ingest_for_translation(
    *,
    source: Path,
    source_language: str,
    target_language: str,
    backend: str,
    default_text_role: str = "",
) -> Dict[str, Any]:
    source = Path(source).resolve()

    if not source.is_file():
        raise RuntimeIngestError(
            "source file not found: {}".format(
                source
            )
        )

    _validate_languages(
        source_language,
        target_language,
    )

    text_role = _validate_text_role(
        default_text_role
    )

    source_info = read_document(
        source
    )

    units = build_translation_units(
        source_info,
        source_language,
        target_language,
        text_role,
    )

    ingest_report = build_ingest_report(
        source,
        source_info,
        backend,
        len(units),
    )

    try:
        intake = (
            build_translation_review_intake(
                units,
                "TRANSLATE",
                source_language=
                    source_language,
                target_language=
                    target_language,
                default_text_role=
                    text_role,
            )
        )
    except ValueError as exc:
        raise RuntimeIngestError(
            "translation intake routing failed: "
            + str(exc)
        ) from exc

    schema_errors = (
        validate_translation_review_intake(
            intake
        )
    )

    cross_errors = (
        intake_cross_errors(
            intake
        )
    )

    errors = (
        list(schema_errors)
        + list(cross_errors)
    )

    if errors:
        raise RuntimeIngestError(
            "invalid PRE_TRANSLATION intake: "
            + "; ".join(errors)
        )

    if (
        intake.get("phase")
        != "PRE_TRANSLATION"
    ):
        raise RuntimeIngestError(
            "ingest unexpectedly escaped "
            "PRE_TRANSLATION phase"
        )

    handoff = (
        intake.get("handoff")
        or {}
    )

    if (
        handoff.get("status")
        != "READY_FOR_TRANSLATION"
        or handoff.get("next_state")
        != "TRANSLATION"
    ):
        raise RuntimeIngestError(
            "PRE_TRANSLATION handoff is not "
            "READY_FOR_TRANSLATION"
        )

    deterministic_qa = (
        intake.get(
            "deterministic_qa"
        )
        or {}
    )

    if (
        deterministic_qa.get("status")
        != "NOT_RUN"
        or deterministic_qa.get(
            "report"
        )
        is not None
    ):
        raise RuntimeIngestError(
            "deterministic bilingual QA must "
            "not run before translation"
        )

    return {
        "format_version": "1.0",
        "source": {
            "filename":
                source_info["filename"],
            "sha256":
                source_info["sha256"],
            "format":
                source_info["format"],
            "coverage":
                source_info.get(
                    "coverage"
                ),
            "native_export": bool(
                source_info.get(
                    "native_export"
                )
            ),
        },
        "ingest_report":
            ingest_report,
        "units": units,
        "pre_translation_intake":
            intake,
    }

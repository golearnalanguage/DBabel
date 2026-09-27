"""Post-translation deterministic QA for DBabel Runtime.

AI suggestions are selected as temporary QA targets. They remain proposals and
never become human approval or approved_target.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_translation_review_intake import (  # noqa: E402
    build_translation_review_intake,
    intake_cross_errors,
    validate_translation_review_intake,
)
from prepare_review_qa import (  # noqa: E402
    prepare_units,
)


class PostTranslationError(ValueError):
    pass


def _validate_translation_result(
    value: Dict[str, Any],
) -> List[Dict[str, Any]]:
    if not isinstance(value, dict):
        raise PostTranslationError(
            "translation result must be an object"
        )

    if value.get("status") != "TRANSLATION_PROPOSED":
        raise PostTranslationError(
            "post-translation QA requires "
            "TRANSLATION_PROPOSED"
        )

    if value.get("completion_allowed") is not False:
        raise PostTranslationError(
            "translation proposal must not allow completion"
        )

    units = value.get("units")

    if not isinstance(units, list) or not units:
        raise PostTranslationError(
            "translation proposal has no units"
        )

    for index, unit in enumerate(units, 1):
        if not isinstance(unit, dict):
            raise PostTranslationError(
                "unit {} is not an object".format(index)
            )

        unit_id = unit.get("id") or index

        if "approved_target" in unit:
            raise PostTranslationError(
                "{} unexpectedly contains approved_target".format(
                    unit_id
                )
            )

        suggested = unit.get("suggested_target")

        if (
            not isinstance(suggested, str)
            or not suggested.strip()
        ):
            raise PostTranslationError(
                "{} has no suggested_target".format(
                    unit_id
                )
            )

    return units


def prepare_post_translation(
    translation_result: Dict[str, Any],
    *,
    source_language: str,
    target_language: str,
    glossary: Optional[Dict[str, Any]] = None,
    default_text_role: Optional[str] = None,
) -> Dict[str, Any]:
    units = _validate_translation_result(
        translation_result
    )

    try:
        qa_units, selection_receipt = (
            prepare_units(
                units,
                "TRANSLATE",
            )
        )
    except ValueError as exc:
        raise PostTranslationError(
            "QA target preparation failed: "
            + str(exc)
        ) from exc

    # prepare_review_qa must select suggested_target for
    # proposal-only units. It must never fabricate approval.
    selection_by_id = {
        item["unit_id"]: item
        for item in selection_receipt["selection"]
    }

    for unit in units:
        selection = selection_by_id.get(
            unit["id"]
        )

        if selection is None:
            raise PostTranslationError(
                "missing QA selection for {}".format(
                    unit["id"]
                )
            )

        if (
            selection["selected_from"]
            != "suggested_target"
        ):
            raise PostTranslationError(
                "{} QA target came from {}, expected "
                "suggested_target".format(
                    unit["id"],
                    selection["selected_from"],
                )
            )

    try:
        intake = build_translation_review_intake(
            qa_units,
            "TRANSLATE",
            glossary=glossary,
            source_language=source_language,
            target_language=target_language,
            default_text_role=default_text_role,
        )
    except ValueError as exc:
        raise PostTranslationError(
            "POST_TRANSLATION intake failed: "
            + str(exc)
        ) from exc

    errors = list(
        validate_translation_review_intake(
            intake
        )
    )

    errors.extend(
        intake_cross_errors(
            intake
        )
    )

    if errors:
        raise PostTranslationError(
            "invalid POST_TRANSLATION intake: "
            + "; ".join(errors)
        )

    if intake.get("phase") != "POST_TRANSLATION":
        raise PostTranslationError(
            "expected POST_TRANSLATION phase, got {!r}".format(
                intake.get("phase")
            )
        )

    deterministic = (
        intake.get("deterministic_qa")
        or {}
    )

    if deterministic.get("status") != "RUN":
        raise PostTranslationError(
            "POST_TRANSLATION must run deterministic QA"
        )

    report = deterministic.get("report")

    if not isinstance(report, dict):
        raise PostTranslationError(
            "POST_TRANSLATION has no deterministic QA report"
        )

    handoff = (
        intake.get("handoff")
        or {}
    )

    if (
        handoff.get("status")
        != "READY_FOR_SEMANTIC_ADJUDICATION"
        or handoff.get("next_state")
        != "ADJUDICATION"
    ):
        raise PostTranslationError(
            "POST_TRANSLATION handoff is invalid"
        )

    # Build a compact issue index without mutating the
    # proposal units themselves.
    issues_by_unit: Dict[str, List[str]] = {
        unit["id"]: []
        for unit in units
    }

    for issue in report.get("issues", []):
        unit_id = issue.get("unit_id")
        issue_id = issue.get("id")

        if (
            unit_id in issues_by_unit
            and isinstance(issue_id, str)
        ):
            issues_by_unit[
                unit_id
            ].append(issue_id)

    review_units = []

    for unit in units:
        value = dict(unit)

        # target remains its original pre-translation value.
        # suggested_target remains the AI proposal.
        value["qa_issue_ids"] = list(
            issues_by_unit[
                unit["id"]
            ]
        )

        if "approved_target" in value:
            raise PostTranslationError(
                "{} unexpectedly acquired approved_target".format(
                    unit["id"]
                )
            )

        review_units.append(value)

    return {
        "format_version": "1.0",
        "status": "POST_TRANSLATION_QA_READY",
        "completion_allowed": False,
        "review_units": review_units,
        "qa_target_units": qa_units,
        "qa_target_receipt": selection_receipt,
        "translation_review_intake": intake,
        "deterministic_qa": report,
        "handoff": handoff,
    }

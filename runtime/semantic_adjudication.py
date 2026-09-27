"""Fail-closed semantic adjudication for DBabel translation proposals.

This layer may identify semantic concerns for human review. It does not create
human approval and, without authoritative evidence, it does not issue verified
KEEP or REPLACE conclusions.
"""
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence

from providers.base import (
    ProviderError,
    TextGenerationProvider,
)
from runtime.models import GenerationRequest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from validate_report import validate_report  # noqa: E402


CLASSIFICATIONS = {
    "GENERIC_DB",
    "STANDARD_SQL",
    "VENDOR_CONCEPT",
    "PRODUCT_NAME",
    "UI_LABEL",
    "SQL_PARAM_IDENTIFIER",
    "COMMAND_PATH_FILENAME",
    "ACRONYM",
    "AMBIGUOUS_HIGH_RISK",
    "PROTOCOL",
    "SECURITY_TERM",
    "CLOUD_SERVICE_NAME",
    "MARKETING_NAME",
    "STANDARD_GENERAL",
    "TECHNICAL_CLAIM",
}

OUTCOMES = {
    "NO_FINDING",
    "REVIEW",
    "OUT_OF_SCOPE_CLAIM",
}

ROOT_KEYS = {"units"}

UNIT_KEYS = {
    "id",
    "outcome",
    "classification",
    "reason",
    "next_action",
}


class SemanticAdjudicationError(ValueError):
    pass


@dataclass(frozen=True)
class SemanticLimits:
    max_units_per_batch: int = 20
    max_chars_per_batch: int = 16000

    def validate(self) -> None:
        if (
            type(self.max_units_per_batch) is not int
            or not 1 <= self.max_units_per_batch <= 100
        ):
            raise SemanticAdjudicationError(
                "max_units_per_batch must be an integer from 1 to 100"
            )

        if (
            type(self.max_chars_per_batch) is not int
            or not 512 <= self.max_chars_per_batch <= 100000
        ):
            raise SemanticAdjudicationError(
                "max_chars_per_batch must be an integer from 512 to 100000"
            )


def _sha256(text: str) -> str:
    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


def _validate_input(
    post_translation: Dict[str, Any],
) -> List[Dict[str, Any]]:
    if not isinstance(post_translation, dict):
        raise SemanticAdjudicationError(
            "post-translation result must be an object"
        )

    if (
        post_translation.get("status")
        != "POST_TRANSLATION_QA_READY"
    ):
        raise SemanticAdjudicationError(
            "semantic adjudication requires POST_TRANSLATION_QA_READY"
        )

    if (
        post_translation.get("completion_allowed")
        is not False
    ):
        raise SemanticAdjudicationError(
            "post-translation result must not allow completion"
        )

    units = post_translation.get("review_units")

    if not isinstance(units, list) or not units:
        raise SemanticAdjudicationError(
            "semantic adjudication requires review units"
        )

    seen = set()

    for index, unit in enumerate(units, 1):
        if not isinstance(unit, dict):
            raise SemanticAdjudicationError(
                "unit {} is not an object".format(index)
            )

        unit_id = str(unit.get("id") or "")

        if not unit_id:
            raise SemanticAdjudicationError(
                "unit {} has no id".format(index)
            )

        if unit_id in seen:
            raise SemanticAdjudicationError(
                "duplicate unit id: {}".format(unit_id)
            )

        seen.add(unit_id)

        if "approved_target" in unit:
            raise SemanticAdjudicationError(
                "{} unexpectedly contains approved_target".format(
                    unit_id
                )
            )

        if not str(
            unit.get("suggested_target") or ""
        ).strip():
            raise SemanticAdjudicationError(
                "{} has no suggested_target".format(
                    unit_id
                )
            )

        context = unit.get("context") or {}

        if not str(
            context.get("text_role") or ""
        ).strip():
            raise SemanticAdjudicationError(
                "{} has no concrete text role".format(
                    unit_id
                )
            )

    return units


def _qa_issue_map(
    post_translation: Dict[str, Any],
) -> Dict[str, List[Dict[str, Any]]]:
    result: Dict[
        str,
        List[Dict[str, Any]]
    ] = {}

    report = (
        post_translation.get(
            "deterministic_qa"
        )
        or {}
    )

    for issue in report.get("issues") or []:
        if not isinstance(issue, dict):
            continue

        unit_id = str(
            issue.get("unit_id") or ""
        )

        if unit_id:
            result.setdefault(
                unit_id,
                [],
            ).append(issue)

    return result


def _unit_chars(
    unit: Dict[str, Any],
) -> int:
    return (
        len(str(unit.get("source") or ""))
        + len(
            str(
                unit.get(
                    "suggested_target"
                )
                or ""
            )
        )
    )


def batch_units(
    units: Sequence[Dict[str, Any]],
    limits: SemanticLimits,
) -> List[List[Dict[str, Any]]]:
    limits.validate()

    batches: List[
        List[Dict[str, Any]]
    ] = []

    current: List[
        Dict[str, Any]
    ] = []

    chars = 0

    for unit in units:
        unit_chars = _unit_chars(unit)

        if unit_chars > limits.max_chars_per_batch:
            raise SemanticAdjudicationError(
                "{} exceeds semantic batch character limit".format(
                    unit["id"]
                )
            )

        if (
            current
            and (
                len(current)
                >= limits.max_units_per_batch
                or chars + unit_chars
                > limits.max_chars_per_batch
            )
        ):
            batches.append(current)
            current = []
            chars = 0

        current.append(unit)
        chars += unit_chars

    if current:
        batches.append(current)

    return batches


SYSTEM_PROMPT = """You are DBabel's semantic-risk adjudication component.
You inspect translation proposals for risks that require human attention.
You do not approve translations.
You do not create approved_target.
You do not issue verified KEEP or REPLACE conclusions.
Without authoritative opened evidence, semantic concerns must remain REVIEW
or OUT_OF_SCOPE_CLAIM.
Return exactly one JSON object and no Markdown or surrounding prose."""


def build_request(
    batch: Sequence[Dict[str, Any]],
    issue_map: Dict[
        str,
        List[Dict[str, Any]]
    ],
    source_language: str,
    target_language: str,
) -> GenerationRequest:
    payload = {
        "task":
            "DBabel semantic risk adjudication",
        "source_language":
            source_language,
        "target_language":
            target_language,
        "rules": [
            "Return exactly one result per supplied unit.",
            "Keep ids unchanged and in the same order.",
            "NO_FINDING means no semantic concern was identified; it is not approval.",
            "Use REVIEW for unresolved ambiguity, terminology, meaning, register, or context risk.",
            "Use OUT_OF_SCOPE_CLAIM for a technical claim requiring separate factual verification.",
            "Never return REPLACE, KEEP, approval, or repaired wording.",
        ],
        "units": [
            {
                "id": unit["id"],
                "location":
                    unit.get("location"),
                "source":
                    unit["source"],
                "suggested_target":
                    unit["suggested_target"],
                "proposal_decision":
                    unit.get(
                        "proposal_decision"
                    ),
                "text_role":
                    (
                        unit.get("context")
                        or {}
                    ).get("text_role"),
                "deterministic_qa_issues":
                    issue_map.get(
                        unit["id"],
                        [],
                    ),
            }
            for unit in batch
        ],
        "response_contract": {
            "units": [{
                "id": "<exact input id>",
                "outcome":
                    "NO_FINDING|REVIEW|OUT_OF_SCOPE_CLAIM",
                "classification":
                    "<DBabel classification or null>",
                "reason":
                    "<brief non-empty reason>",
                "next_action":
                    "<required for REVIEW/OUT_OF_SCOPE_CLAIM; empty for NO_FINDING>",
            }]
        },
    }

    return GenerationRequest(
        system=SYSTEM_PROMPT,
        user=json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        temperature=0.1,
    )


def parse_response(
    text: str,
    expected_batch: Sequence[
        Dict[str, Any]
    ],
) -> List[Dict[str, Any]]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SemanticAdjudicationError(
            "semantic provider output is not strict JSON"
        ) from exc

    if (
        not isinstance(value, dict)
        or set(value) != ROOT_KEYS
    ):
        raise SemanticAdjudicationError(
            "semantic output root keys must be exactly: units"
        )

    items = value["units"]

    if not isinstance(items, list):
        raise SemanticAdjudicationError(
            "semantic output units must be an array"
        )

    expected_ids = [
        unit["id"]
        for unit in expected_batch
    ]

    returned_ids = []

    for index, item in enumerate(
        items,
        1,
    ):
        if (
            not isinstance(item, dict)
            or set(item) != UNIT_KEYS
        ):
            raise SemanticAdjudicationError(
                "semantic result {} has unexpected or missing keys".format(
                    index
                )
            )

        unit_id = item.get("id")

        if not isinstance(unit_id, str):
            raise SemanticAdjudicationError(
                "semantic result {} has invalid id".format(
                    index
                )
            )

        returned_ids.append(unit_id)

    if returned_ids != expected_ids:
        raise SemanticAdjudicationError(
            "semantic unit ids do not exactly match requested order and membership"
        )

    results = []

    for item in items:
        outcome = item["outcome"]
        classification = item["classification"]
        reason = item["reason"]
        next_action = item["next_action"]

        if outcome not in OUTCOMES:
            raise SemanticAdjudicationError(
                "{} has forbidden semantic outcome {!r}".format(
                    item["id"],
                    outcome,
                )
            )

        if (
            not isinstance(reason, str)
            or not reason.strip()
        ):
            raise SemanticAdjudicationError(
                "{} has no semantic reason".format(
                    item["id"]
                )
            )

        if not isinstance(next_action, str):
            raise SemanticAdjudicationError(
                "{} has invalid next_action".format(
                    item["id"]
                )
            )

        if outcome == "NO_FINDING":
            if classification is not None:
                raise SemanticAdjudicationError(
                    "{} NO_FINDING requires null classification".format(
                        item["id"]
                    )
                )

            if next_action:
                raise SemanticAdjudicationError(
                    "{} NO_FINDING requires empty next_action".format(
                        item["id"]
                    )
                )

        else:
            if classification not in CLASSIFICATIONS:
                raise SemanticAdjudicationError(
                    "{} has invalid classification {!r}".format(
                        item["id"],
                        classification,
                    )
                )

            if not next_action.strip():
                raise SemanticAdjudicationError(
                    "{} {} requires next_action".format(
                        item["id"],
                        outcome,
                    )
                )

            if (
                outcome
                == "OUT_OF_SCOPE_CLAIM"
                and classification
                != "TECHNICAL_CLAIM"
            ):
                raise SemanticAdjudicationError(
                    "{} OUT_OF_SCOPE_CLAIM must use TECHNICAL_CLAIM".format(
                        item["id"]
                    )
                )

        results.append(dict(item))

    return results


def _build_report(
    *,
    document_name: str,
    units: Sequence[Dict[str, Any]],
    outcomes: Sequence[Dict[str, Any]],
    post_translation: Dict[str, Any],
) -> Dict[str, Any]:
    by_id = {
        unit["id"]: unit
        for unit in units
    }

    findings = []

    finding_index = 0

    for result in outcomes:
        if result["outcome"] == "NO_FINDING":
            continue

        finding_index += 1

        unit = by_id[
            result["id"]
        ]

        classification = (
            result["classification"]
        )

        finding = {
            "id":
                "SF{:04d}".format(
                    finding_index
                ),
            "location":
                str(
                    unit.get("location")
                    or "unit:"
                    + unit["id"]
                ),
            "original":
                unit[
                    "suggested_target"
                ],
            "text_role":
                str(
                    (
                        unit.get("context")
                        or {}
                    ).get(
                        "text_role"
                    )
                ),
            "classification":
                classification,
            "decision":
                result["outcome"],
            "reason":
                result["reason"],
            "confidence":
                "REVIEW_REQUIRED",
            "protected":
                classification in {
                    "SQL_PARAM_IDENTIFIER",
                    "COMMAND_PATH_FILENAME",
                },
            "verification_required":
                True,
            "evidence_refs": [],
            "next_action":
                result["next_action"],
        }

        if (
            result["outcome"]
            == "OUT_OF_SCOPE_CLAIM"
        ):
            finding[
                "technical_claim"
            ] = True

        findings.append(finding)

    deterministic = (
        post_translation.get(
            "deterministic_qa"
        )
        or {}
    )

    summary = (
        deterministic.get("summary")
        or {}
    )

    report = {
        "dbabel_version": "1.5.0",
        "mode": "TRANSLATE",
        "status":
            "COMPLETED_WITH_REVIEW",
        "document":
            document_name,
        "scope_summary":
            "Model-assisted semantic-risk review of {} translation proposal unit(s).".format(
                len(units)
            ),
        "findings":
            findings,
        "limitations": [
            "Semantic adjudication is model-assisted and does not constitute human approval.",
            "No authoritative external source was opened during this adjudication stage.",
        ],
        "sources": [],
        "coverage": {
            "status": "PARTIAL",
            "inspected": [
                "{} translation proposal unit(s) with bound deterministic QA context".format(
                    len(units)
                )
            ],
            "uninspected": [
                "Authoritative external terminology and product/version evidence was not independently opened."
            ],
        },
        "qa": {
            "status": "PASS",
            "checks": [
                {
                    "name":
                        "semantic_output_contract",
                    "status": "PASS",
                    "note":
                        "Every input unit received one schema-constrained semantic outcome.",
                },
                {
                    "name":
                        "deterministic_qa_binding",
                    "status": "PASS",
                    "note":
                        "Bound deterministic QA summary: {} error(s), {} warning(s).".format(
                            summary.get(
                                "error_count",
                                0,
                            ),
                            summary.get(
                                "warning_count",
                                0,
                            ),
                        ),
                },
            ],
        },
        "repair": {
            "status": "NOT_REQUESTED",
            "authorized": False,
            "changes": [],
            "round_trip_qa": {
                "status": "NOT_RUN",
                "checks": [{
                    "name":
                        "reopen_output",
                    "status":
                        "NOT_APPLICABLE",
                    "note":
                        "No repair or export occurred during semantic adjudication.",
                }],
            },
            "note":
                "Semantic adjudication is proposal review only; no repair was requested.",
        },
        "next_actions": [
            "Bind semantic findings and deterministic QA into the Full Local Review Workbench.",
            "Collect human review decisions before any final export.",
        ],
        "glossary_candidates": [],
    }

    errors = validate_report(
        report
    )

    if errors:
        raise SemanticAdjudicationError(
            "generated audit report violates DBabel contract: "
            + "; ".join(errors)
        )

    return report


def adjudicate_semantics(
    *,
    provider: TextGenerationProvider,
    post_translation: Dict[str, Any],
    source_language: str,
    target_language: str,
    document_name: str,
    limits: SemanticLimits = SemanticLimits(),
) -> Dict[str, Any]:
    units = _validate_input(
        post_translation
    )

    if (
        not source_language
        or not target_language
        or source_language.casefold()
        == target_language.casefold()
    ):
        raise SemanticAdjudicationError(
            "semantic adjudication requires distinct explicit languages"
        )

    issue_map = _qa_issue_map(
        post_translation
    )

    batches = batch_units(
        units,
        limits,
    )

    outcomes: List[
        Dict[str, Any]
    ] = []

    receipts = []

    for batch_index, batch in enumerate(
        batches,
        1,
    ):
        request = build_request(
            batch,
            issue_map,
            source_language,
            target_language,
        )

        try:
            response = provider.generate(
                request
            )
        except (
            ProviderError,
            OSError,
            ValueError,
        ) as exc:
            raise SemanticAdjudicationError(
                "semantic provider failed for batch {}: {}".format(
                    batch_index,
                    exc,
                )
            ) from exc

        batch_outcomes = (
            parse_response(
                response.text,
                batch,
            )
        )

        outcomes.extend(
            batch_outcomes
        )

        receipts.append({
            "batch_index":
                batch_index,
            "unit_ids": [
                unit["id"]
                for unit in batch
            ],
            "request_sha256":
                _sha256(request.user),
            "response_sha256":
                _sha256(
                    response.text
                ),
            "provider":
                response.provider,
            "model":
                response.model,
            "response_id":
                response.response_id,
            "usage":
                dict(response.usage),
        })

    expected_ids = [
        unit["id"]
        for unit in units
    ]

    if [
        item["id"]
        for item in outcomes
    ] != expected_ids:
        raise SemanticAdjudicationError(
            "semantic result sequence does not match review units"
        )

    report = _build_report(
        document_name=
            document_name,
        units=units,
        outcomes=outcomes,
        post_translation=
            post_translation,
    )

    return {
        "format_version": "1.0",
        "status":
            "SEMANTIC_ADJUDICATION_READY",
        "completion_allowed": False,
        "unit_count": len(units),
        "finding_count":
            len(
                report["findings"]
            ),
        "outcomes":
            outcomes,
        "receipts":
            receipts,
        "audit_report":
            report,
        "next_state":
            "REVIEW_SESSION_BINDING",
    }

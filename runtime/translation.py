"""Bounded, fail-closed AI translation generation for DBabel Runtime.

AI output is a proposal only. This module never creates approved_target,
human decisions, evidence, or workflow completion.
"""
from __future__ import annotations

from collections import Counter
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

from check_bilingual_integrity import (  # noqa: E402
    extract_cli_options,
    extract_env_vars,
    extract_filenames,
    extract_paths,
    extract_placeholders,
    extract_urls,
    extract_versions,
)


ALLOWED_PROPOSAL_DECISIONS = {
    "REPLACE",
    "PROTECT",
    "REVIEW",
}

ROOT_KEYS = {"units"}

UNIT_KEYS = {
    "id",
    "suggested_target",
    "proposal_decision",
    "reason",
}


class RuntimeTranslationError(ValueError):
    pass


@dataclass(frozen=True)
class TranslationLimits:
    max_units_per_batch: int = 20
    max_source_chars_per_batch: int = 12000

    def validate(self) -> None:
        if (
            type(self.max_units_per_batch) is not int
            or not 1 <= self.max_units_per_batch <= 100
        ):
            raise RuntimeTranslationError(
                "max_units_per_batch must be an integer from 1 to 100"
            )

        if (
            type(self.max_source_chars_per_batch) is not int
            or not 256
            <= self.max_source_chars_per_batch
            <= 100000
        ):
            raise RuntimeTranslationError(
                "max_source_chars_per_batch must be "
                "an integer from 256 to 100000"
            )


def sha256_text(text: str) -> str:
    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


def protected_literals(text: str) -> List[str]:
    """Return stable unique protected strings from existing DBabel extractors."""
    extractors = (
        extract_placeholders,
        extract_urls,
        extract_paths,
        extract_filenames,
        extract_cli_options,
        extract_env_vars,
        extract_versions,
    )

    values: List[str] = []
    seen = set()

    for extractor in extractors:
        for raw in extractor(text):
            value = str(raw)

            if not value or value in seen:
                continue

            seen.add(value)
            values.append(value)

    # Longest first makes diagnostic output easier to interpret
    # when one protected token is a substring of another.
    return sorted(
        values,
        key=lambda value: (-len(value), value),
    )


def validate_units_for_translation(
    units: Sequence[Dict[str, Any]],
) -> None:
    if not units:
        raise RuntimeTranslationError(
            "translation requires at least one unit"
        )

    seen = set()

    for index, unit in enumerate(units, 1):
        if not isinstance(unit, dict):
            raise RuntimeTranslationError(
                "unit {} is not an object".format(index)
            )

        unit_id = str(unit.get("id") or "")

        if not unit_id:
            raise RuntimeTranslationError(
                "unit {} has no id".format(index)
            )

        if unit_id in seen:
            raise RuntimeTranslationError(
                "duplicate unit id: {}".format(unit_id)
            )

        seen.add(unit_id)

        source = unit.get("source")

        if not isinstance(source, str) or not source.strip():
            raise RuntimeTranslationError(
                "{} has no translatable source text".format(
                    unit_id
                )
            )

        if str(unit.get("target") or ""):
            raise RuntimeTranslationError(
                "{} is not PRE_TRANSLATION: target is populated".format(
                    unit_id
                )
            )

        context = unit.get("context") or {}
        text_role = context.get("text_role")

        if (
            not isinstance(text_role, str)
            or not text_role.strip()
            or text_role == "ANY"
        ):
            raise RuntimeTranslationError(
                "{} requires a concrete text role".format(
                    unit_id
                )
            )


def batch_units(
    units: Sequence[Dict[str, Any]],
    limits: TranslationLimits,
) -> List[List[Dict[str, Any]]]:
    limits.validate()
    validate_units_for_translation(units)

    batches: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []
    current_chars = 0

    for unit in units:
        source_chars = len(unit["source"])

        if (
            source_chars
            > limits.max_source_chars_per_batch
        ):
            raise RuntimeTranslationError(
                "{} exceeds max_source_chars_per_batch".format(
                    unit["id"]
                )
            )

        would_exceed_units = (
            len(current)
            >= limits.max_units_per_batch
        )

        would_exceed_chars = (
            current
            and current_chars + source_chars
            > limits.max_source_chars_per_batch
        )

        if (
            would_exceed_units
            or would_exceed_chars
        ):
            batches.append(current)
            current = []
            current_chars = 0

        current.append(unit)
        current_chars += source_chars

    if current:
        batches.append(current)

    return batches


def _request_payload(
    batch: Sequence[Dict[str, Any]],
    source_language: str,
    target_language: str,
) -> Dict[str, Any]:
    return {
        "task": "DBabel bounded technical translation proposal",
        "source_language": source_language,
        "target_language": target_language,
        "rules": [
            "Return JSON only.",
            "Return exactly one result for every supplied unit.",
            "Keep unit ids unchanged and in the same order.",
            "Do not create human approval or approved_target.",
            "Preserve every protected literal exactly.",
            "Use REPLACE for a translation proposal.",
            "Use PROTECT only when the source should remain unchanged.",
            "Use REVIEW when a reliable translation cannot be proposed.",
        ],
        "units": [
            {
                "id": unit["id"],
                "source": unit["source"],
                "text_role": (
                    unit.get("context")
                    or {}
                )["text_role"],
                "protected_literals":
                    protected_literals(
                        unit["source"]
                    ),
            }
            for unit in batch
        ],
        "response_contract": {
            "units": [
                {
                    "id": "<exact input id>",
                    "suggested_target": "<string>",
                    "proposal_decision":
                        "REPLACE|PROTECT|REVIEW",
                    "reason": "<brief string>",
                }
            ]
        },
    }


SYSTEM_PROMPT = """You are the generation component inside DBabel.
Produce technical translation proposals only.
You do not approve translations and you do not make human review decisions.
Obey the supplied JSON contract exactly.
Preserve protected literals byte-for-byte.
Return one JSON object and no surrounding prose or Markdown fences."""


def build_generation_request(
    batch: Sequence[Dict[str, Any]],
    source_language: str,
    target_language: str,
) -> GenerationRequest:
    payload = _request_payload(
        batch,
        source_language,
        target_language,
    )

    return GenerationRequest(
        system=SYSTEM_PROMPT,
        user=json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        temperature=0.1,
    )


def _verify_literal_preservation(
    source: str,
    target: str,
    unit_id: str,
) -> None:
    for literal in protected_literals(source):
        source_count = source.count(literal)
        target_count = target.count(literal)

        if source_count != target_count:
            raise RuntimeTranslationError(
                "{} changed protected literal {!r}: "
                "source count {}, target count {}".format(
                    unit_id,
                    literal,
                    source_count,
                    target_count,
                )
            )


def parse_batch_response(
    text: str,
    expected_batch: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeTranslationError(
            "provider output is not strict JSON"
        ) from exc

    if not isinstance(value, dict):
        raise RuntimeTranslationError(
            "provider output root must be an object"
        )

    if set(value) != ROOT_KEYS:
        raise RuntimeTranslationError(
            "provider output root keys must be exactly: units"
        )

    returned = value["units"]

    if not isinstance(returned, list):
        raise RuntimeTranslationError(
            "provider output units must be an array"
        )

    expected_ids = [
        unit["id"]
        for unit in expected_batch
    ]

    returned_ids = []

    for index, item in enumerate(returned, 1):
        if not isinstance(item, dict):
            raise RuntimeTranslationError(
                "provider result {} is not an object".format(
                    index
                )
            )

        if set(item) != UNIT_KEYS:
            raise RuntimeTranslationError(
                "provider result {} has unexpected or missing keys".format(
                    index
                )
            )

        unit_id = item.get("id")

        if not isinstance(unit_id, str):
            raise RuntimeTranslationError(
                "provider result {} has invalid id".format(
                    index
                )
            )

        returned_ids.append(unit_id)

    if returned_ids != expected_ids:
        raise RuntimeTranslationError(
            "provider unit ids do not exactly match "
            "the requested order and membership"
        )

    expected_by_id = {
        unit["id"]: unit
        for unit in expected_batch
    }

    proposals = []

    for item in returned:
        unit_id = item["id"]

        suggested = item.get(
            "suggested_target"
        )

        decision = item.get(
            "proposal_decision"
        )

        reason = item.get("reason")

        if (
            not isinstance(suggested, str)
            or not suggested.strip()
        ):
            raise RuntimeTranslationError(
                "{} has empty suggested_target".format(
                    unit_id
                )
            )

        if decision not in ALLOWED_PROPOSAL_DECISIONS:
            raise RuntimeTranslationError(
                "{} has unsupported proposal_decision {!r}".format(
                    unit_id,
                    decision,
                )
            )

        if (
            not isinstance(reason, str)
            or not reason.strip()
        ):
            raise RuntimeTranslationError(
                "{} has no proposal reason".format(
                    unit_id
                )
            )

        source = expected_by_id[
            unit_id
        ]["source"]

        if (
            decision == "REPLACE"
            and suggested == source
        ):
            raise RuntimeTranslationError(
                "{} REPLACE proposal is identical to source".format(
                    unit_id
                )
            )

        if (
            decision == "PROTECT"
            and suggested != source
        ):
            raise RuntimeTranslationError(
                "{} PROTECT proposal must preserve source exactly".format(
                    unit_id
                )
            )

        _verify_literal_preservation(
            source,
            suggested,
            unit_id,
        )

        proposals.append({
            "id": unit_id,
            "suggested_target": suggested,
            "proposal_decision": decision,
            "suggestion_reason": reason,
        })

    return proposals


def translate_units(
    *,
    provider: TextGenerationProvider,
    units: Sequence[Dict[str, Any]],
    source_language: str,
    target_language: str,
    limits: TranslationLimits = TranslationLimits(),
) -> Dict[str, Any]:
    if (
        not source_language
        or not target_language
        or source_language.casefold()
        == target_language.casefold()
    ):
        raise RuntimeTranslationError(
            "translation requires distinct explicit languages"
        )

    batches = batch_units(
        units,
        limits,
    )

    proposal_by_id: Dict[
        str,
        Dict[str, Any]
    ] = {}

    receipts = []

    for batch_index, batch in enumerate(
        batches,
        1,
    ):
        request = build_generation_request(
            batch,
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
            raise RuntimeTranslationError(
                "provider generation failed for batch {}: {}".format(
                    batch_index,
                    exc,
                )
            ) from exc

        proposals = parse_batch_response(
            response.text,
            batch,
        )

        for proposal in proposals:
            unit_id = proposal["id"]

            if unit_id in proposal_by_id:
                raise RuntimeTranslationError(
                    "duplicate proposal across batches: {}".format(
                        unit_id
                    )
                )

            proposal_by_id[
                unit_id
            ] = proposal

        receipts.append({
            "batch_index": batch_index,
            "unit_ids": [
                unit["id"]
                for unit in batch
            ],
            "request_sha256":
                sha256_text(request.user),
            "response_sha256":
                sha256_text(response.text),
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

    if list(proposal_by_id) != expected_ids:
        raise RuntimeTranslationError(
            "final proposal sequence does not match source units"
        )

    proposed_units = []

    for unit in units:
        proposal = proposal_by_id[
            unit["id"]
        ]

        value = dict(unit)

        # target remains untouched. AI output is proposal-only.
        value["suggested_target"] = (
            proposal["suggested_target"]
        )
        value["proposal_decision"] = (
            proposal["proposal_decision"]
        )
        value["suggestion_reason"] = (
            proposal["suggestion_reason"]
        )

        if "approved_target" in value:
            raise RuntimeTranslationError(
                "{} unexpectedly contains approved_target".format(
                    unit["id"]
                )
            )

        proposed_units.append(value)

    return {
        "format_version": "1.0",
        "status": "TRANSLATION_PROPOSED",
        "completion_allowed": False,
        "batch_count": len(batches),
        "unit_count": len(proposed_units),
        "units": proposed_units,
        "receipts": receipts,
    }

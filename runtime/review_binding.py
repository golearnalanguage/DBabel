"""Bind DBabel translation proposals into a Full Workbench review session.

The source-layout copy used as current_target is an anchoring mechanism only.
It is not a translation, approval, or completed target.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from runtime.project import (
    atomic_write_json,
    sha256_file,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(
        0,
        str(SCRIPTS),
    )

from validate_translate_delivery import (  # noqa: E402
    validate_delivery,
)


NATIVE_TRANSLATE_FORMATS = {
    "docx",
    "txt",
    "md",
    "xlsx",
}


class ReviewBindingError(ValueError):
    pass


def _unit_ids(
    units: Any,
    label: str,
) -> List[str]:
    if not isinstance(units, list) or not units:
        raise ReviewBindingError(
            "{} must contain at least one unit".format(
                label
            )
        )

    result = []

    for index, unit in enumerate(
        units,
        1,
    ):
        if not isinstance(unit, dict):
            raise ReviewBindingError(
                "{} unit {} is not an object".format(
                    label,
                    index,
                )
            )

        unit_id = str(
            unit.get("id")
            or ""
        )

        if not unit_id:
            raise ReviewBindingError(
                "{} unit {} has no id".format(
                    label,
                    index,
                )
            )

        result.append(unit_id)

    if len(result) != len(set(result)):
        raise ReviewBindingError(
            "{} contains duplicate unit ids".format(
                label
            )
        )

    return result


def _artifact(
    path: Path,
) -> Dict[str, str]:
    return {
        "path": str(path),
        "sha256": sha256_file(
            path
        ),
    }


def bind_review_session(
    *,
    repo_root: Path,
    run_root: Path,
    source: Path,
    source_info: Dict[str, Any],
    post_translation: Dict[str, Any],
    semantic_result: Dict[str, Any],
    title: Optional[str] = None,
) -> Dict[str, Any]:
    repo_root = Path(
        repo_root
    ).resolve()

    run_root = Path(
        run_root
    ).resolve()

    source = Path(
        source
    ).resolve()

    if not source.is_file():
        raise ReviewBindingError(
            "source file not found: {}".format(
                source
            )
        )

    expected_source_sha = str(
        source_info.get(
            "sha256"
        )
        or ""
    )

    if not expected_source_sha:
        raise ReviewBindingError(
            "source_info has no sha256"
        )

    if (
        sha256_file(source)
        != expected_source_sha
    ):
        raise ReviewBindingError(
            "source hash does not match ingest source"
        )

    source_format = str(
        source_info.get(
            "format"
        )
        or ""
    ).lower()

    if (
        source_info.get(
            "native_export"
        )
        is not True
    ):
        raise ReviewBindingError(
            "Full TRANSLATE binding requires native_export capability"
        )

    if (
        source_format
        not in NATIVE_TRANSLATE_FORMATS
    ):
        raise ReviewBindingError(
            "unsupported native TRANSLATE format: {}".format(
                source_format
            )
        )

    if (
        post_translation.get(
            "status"
        )
        != "POST_TRANSLATION_QA_READY"
    ):
        raise ReviewBindingError(
            "review binding requires POST_TRANSLATION_QA_READY"
        )

    if (
        post_translation.get(
            "completion_allowed"
        )
        is not False
    ):
        raise ReviewBindingError(
            "post-translation stage must not allow completion"
        )

    if (
        semantic_result.get(
            "status"
        )
        != "SEMANTIC_ADJUDICATION_READY"
    ):
        raise ReviewBindingError(
            "review binding requires SEMANTIC_ADJUDICATION_READY"
        )

    if (
        semantic_result.get(
            "completion_allowed"
        )
        is not False
    ):
        raise ReviewBindingError(
            "semantic stage must not allow completion"
        )

    if (
        semantic_result.get(
            "next_state"
        )
        != "REVIEW_SESSION_BINDING"
    ):
        raise ReviewBindingError(
            "semantic stage does not hand off to REVIEW_SESSION_BINDING"
        )

    review_units = (
        post_translation.get(
            "review_units"
        )
    )

    qa_units = (
        post_translation.get(
            "qa_target_units"
        )
    )

    review_ids = _unit_ids(
        review_units,
        "review_units",
    )

    qa_ids = _unit_ids(
        qa_units,
        "qa_target_units",
    )

    semantic_outcomes = (
        semantic_result.get(
            "outcomes"
        )
    )

    semantic_ids = _unit_ids(
        semantic_outcomes,
        "semantic outcomes",
    )

    if not (
        review_ids
        == qa_ids
        == semantic_ids
    ):
        raise ReviewBindingError(
            "review, QA, and semantic unit sequences differ"
        )

    audit_report = semantic_result.get(
        "audit_report"
    )

    if not isinstance(
        audit_report,
        dict,
    ):
        raise ReviewBindingError(
            "semantic result has no audit report"
        )

    if (
        audit_report.get(
            "mode"
        )
        != "TRANSLATE"
    ):
        raise ReviewBindingError(
            "semantic audit report is not TRANSLATE"
        )

    deterministic_qa = (
        post_translation.get(
            "deterministic_qa"
        )
    )

    if not isinstance(
        deterministic_qa,
        dict,
    ):
        raise ReviewBindingError(
            "post-translation result has no deterministic QA report"
        )

    # Native TRANSLATE review uses the original source text
    # as current_target only so native anchors resolve against
    # the untouched source layout. The actual translation
    # proposal remains suggested_target.
    binding_units = []

    for unit in review_units:
        value = dict(unit)

        if "approved_target" in value:
            raise ReviewBindingError(
                "{} unexpectedly contains approved_target".format(
                    unit["id"]
                )
            )

        source_text = str(
            unit.get("source")
            or ""
        )

        suggested = str(
            unit.get(
                "suggested_target"
            )
            or ""
        )

        if not source_text:
            raise ReviewBindingError(
                "{} has empty source".format(
                    unit["id"]
                )
            )

        if not suggested:
            raise ReviewBindingError(
                "{} has no suggested_target".format(
                    unit["id"]
                )
            )

        value["target"] = source_text

        binding_units.append(
            value
        )

    artifacts = {
        "review_units":
            run_root
            / "review-units.json",
        "qa_input":
            run_root
            / "qa-input.json",
        "qa_report":
            run_root
            / "deterministic-qa-report.json",
        "audit_report":
            run_root
            / "audit-report.json",
        "delivery_receipt":
            run_root
            / "delivery-receipt.json",
    }

    bundle = (
        run_root
        / "review.dbreview"
    )

    for path in list(
        artifacts.values()
    ) + [bundle]:
        if path.exists():
            raise ReviewBindingError(
                "review binding output already exists: {}".format(
                    path
                )
            )

    atomic_write_json(
        artifacts["review_units"],
        {
            "units":
                binding_units,
        },
    )

    atomic_write_json(
        artifacts["qa_input"],
        {
            "units":
                qa_units,
        },
    )

    atomic_write_json(
        artifacts["qa_report"],
        deterministic_qa,
    )

    atomic_write_json(
        artifacts["audit_report"],
        audit_report,
    )

    command = [
        sys.executable,
        str(
            repo_root
            / "scripts"
            / "create_review_session.py"
        ),
        str(
            artifacts[
                "review_units"
            ]
        ),
        "--qa-report",
        str(
            artifacts[
                "qa_report"
            ]
        ),
        "--audit-report",
        str(
            artifacts[
                "audit_report"
            ]
        ),
        "--original",
        str(source),
        "--output",
        str(bundle),
        "--title",
        title or source.name,
        "--mode",
        "TRANSLATE",
    ]

    created = subprocess.run(
        command,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )

    if created.returncode != 0:
        detail = (
            created.stderr.strip()
            or created.stdout.strip()
            or "unknown create_review_session failure"
        )

        raise ReviewBindingError(
            "review-session creation failed: "
            + detail
        )

    if not bundle.is_dir():
        raise ReviewBindingError(
            "review-session creation did not produce a .dbreview directory"
        )

    if (
        sha256_file(source)
        != expected_source_sha
    ):
        raise ReviewBindingError(
            "source changed during review binding"
        )

    receipt = validate_delivery(
        bundle,
        repo_root,
        artifacts["qa_input"],
        artifacts["qa_report"],
        artifacts["audit_report"],
        "full",
        False,
    )

    atomic_write_json(
        artifacts[
            "delivery_receipt"
        ],
        receipt,
    )

    if (
        receipt.get("status")
        != "READY_FOR_HUMAN_REVIEW"
    ):
        raise ReviewBindingError(
            "delivery validation blocked: {}".format(
                "; ".join(
                    receipt.get(
                        "errors"
                    )
                    or [
                        str(
                            receipt.get(
                                "status"
                            )
                        )
                    ]
                )
            )
        )

    if (
        receipt.get(
            "completion_allowed"
        )
        is not False
    ):
        raise ReviewBindingError(
            "delivery gate unexpectedly allows completion"
        )

    if (
        receipt.get("surface")
        != "FULL_LOCAL_WORKBENCH_READY"
    ):
        raise ReviewBindingError(
            "Full Local Workbench is not ready"
        )

    session_path = (
        bundle
        / "session.json"
    )

    if not session_path.is_file():
        raise ReviewBindingError(
            "review bundle has no session.json"
        )

    return {
        "format_version": "1.0",
        "status":
            "READY_FOR_HUMAN_REVIEW",
        "completion_allowed": False,
        "surface":
            receipt["surface"],
        "session_id":
            receipt["session_id"],
        "bundle_path":
            str(bundle),
        "artifacts": {
            key:
                _artifact(path)
            for key, path
            in artifacts.items()
        },
        "session":
            _artifact(
                session_path
            ),
        "delivery_receipt":
            receipt,
    }

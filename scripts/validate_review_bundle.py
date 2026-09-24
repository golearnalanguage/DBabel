#!/usr/bin/env python3
"""Validate DBabel .dbreview contracts and internal cross-references."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

if str(HERE) not in sys.path:
    sys.path.insert(
        0,
        str(HERE),
    )

from review_model import (
    load_bundle,
    validate_bundle,
)
from technique_contract import (
    load_translation_registry,
    validate_technique_annotation,
)


def cross_errors(data, root):
    errors = []

    uids = set(
        data["units_by_id"]
    )

    eids = {
        str(item.get("id"))
        for item in data["evidence"]
    }

    issueids = {
        str(item.get("id"))
        for item in data["issues"]
    }

    technique_registry = (
        load_translation_registry(
            root
        )
    )

    for issue in data["issues"]:
        if issue["unit_id"] not in uids:
            errors.append(
                "issue {} references unknown unit {}".format(
                    issue["id"],
                    issue["unit_id"],
                )
            )

        missing = (
            set(
                issue.get(
                    "evidence_refs"
                )
                or []
            )
            - eids
        )

        if missing:
            errors.append(
                "issue {} references unknown evidence {}".format(
                    issue["id"],
                    sorted(missing),
                )
            )

        for technique_error in (
            validate_technique_annotation(
                issue.get(
                    "technique"
                ),
                technique_registry,
            )
        ):
            errors.append(
                "issue {} technique: {}".format(
                    issue["id"],
                    technique_error,
                )
            )

    for unit in data["units"]:
        missing = (
            set(
                unit.get(
                    "finding_refs"
                )
                or []
            )
            | set(
                unit.get(
                    "qa_issue_refs"
                )
                or []
            )
        ) - issueids

        if missing:
            errors.append(
                "unit {} references unknown issues {}".format(
                    unit["id"],
                    sorted(missing),
                )
            )

        missing_ev = (
            set(
                unit.get(
                    "evidence_refs"
                )
                or []
            )
            - eids
        )

        if missing_ev:
            errors.append(
                "unit {} references unknown evidence {}".format(
                    unit["id"],
                    sorted(missing_ev),
                )
            )

    counts = data["session"]["counts"]

    if counts["units"] != len(
        data["units"]
    ):
        errors.append(
            "session unit count mismatch"
        )

    if counts["issues"] != len(
        data["issues"]
    ):
        errors.append(
            "session issue count mismatch"
        )

    if counts["evidence"] != len(
        data["evidence"]
    ):
        errors.append(
            "session evidence count mismatch"
        )

    return errors


def main():
    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "bundle"
    )

    parser.add_argument(
        "--repo-root",
        default=str(ROOT),
    )

    args = parser.parse_args()

    bundle = Path(
        args.bundle
    )

    root = Path(
        args.repo_root
    )

    errors = validate_bundle(
        bundle,
        root,
    )

    data = load_bundle(
        bundle
    )

    errors += cross_errors(
        data,
        root,
    )

    if errors:
        for error in errors:
            print(
                "ERROR:",
                error,
                file=sys.stderr,
            )

        return 1

    print(
        "Review bundle valid: {} units, {} issues, {} evidence records".format(
            len(data["units"]),
            len(data["issues"]),
            len(data["evidence"]),
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )

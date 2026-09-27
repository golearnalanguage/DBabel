#!/usr/bin/env python3
"""Prepare a traceable DBabel TRANSLATE project run."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(
    __file__
).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )

from runtime.orchestrator import (  # noqa: E402
    OrchestrationError,
    RuntimeOrchestrator,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "source",
        type=Path,
    )

    parser.add_argument(
        "--source-language",
        required=True,
    )

    parser.add_argument(
        "--target-language",
        required=True,
    )

    parser.add_argument(
        "--provider-config",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=ROOT / "output" / "runtime",
    )

    parser.add_argument(
        "--declare-backend",
        action="append",
        default=[],
    )

    args = parser.parse_args()

    try:
        manifest = RuntimeOrchestrator(
            repo_root=ROOT,
            workspace_root=args.workspace_root,
        ).prepare_translation(
            source=args.source,
            source_language=
                args.source_language,
            target_language=
                args.target_language,
            provider_config_path=
                args.provider_config,
            declared_backends=
                args.declare_backend,
        )

    except (
        OSError,
        ValueError,
        OrchestrationError,
    ) as exc:
        parser.exit(
            2,
            "DBabel runtime preparation failed: "
            + str(exc)
            + "\n",
        )

    print(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )

    if manifest["status"] == "BLOCKED":
        return 1

    if manifest["status"] != "READY_FOR_INGEST":
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

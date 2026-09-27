#!/usr/bin/env python3
"""Run a traceable DBabel TRANSLATE project to the Full Local Workbench gate."""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
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


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description=__doc__
    )

    value.add_argument(
        "source",
        type=Path,
    )

    value.add_argument(
        "--source-language",
        required=True,
    )

    value.add_argument(
        "--target-language",
        required=True,
    )

    value.add_argument(
        "--text-role",
        required=True,
        help=(
            "Concrete text role for this bounded CLI run, "
            "for example PROSE. ANY is not allowed."
        ),
    )

    value.add_argument(
        "--provider-config",
        required=True,
        type=Path,
    )

    value.add_argument(
        "--workspace-root",
        type=Path,
        default=
            ROOT / "output" / "runtime",
    )

    value.add_argument(
        "--declare-backend",
        action="append",
        default=[],
    )

    value.add_argument(
        "--open-workbench",
        action="store_true",
        help=(
            "After READY_FOR_HUMAN_REVIEW, "
            "start the Full Local Workbench."
        ),
    )

    value.add_argument(
        "--workbench-port",
        type=int,
        default=0,
        help=(
            "Local Workbench port. "
            "0 asks the OS to choose an available port."
        ),
    )

    value.add_argument(
        "--no-browser",
        action="store_true",
        help=(
            "With --open-workbench, print the local URL "
            "without opening a browser."
        ),
    )

    return value


def main() -> int:
    args = parser().parse_args()

    if not 0 <= args.workbench_port <= 65535:
        parser().error(
            "--workbench-port must be from 0 to 65535"
        )

    source = (
        args.source
        .expanduser()
        .resolve()
    )

    try:
        manifest = RuntimeOrchestrator(
            repo_root=ROOT,
            workspace_root=
                args.workspace_root,
        ).run_translation_to_review(
            source=source,
            source_language=
                args.source_language,
            target_language=
                args.target_language,
            provider_config_path=
                args.provider_config,
            default_text_role=
                args.text_role,
            declared_backends=
                args.declare_backend,
        )

    except (
        OSError,
        ValueError,
        OrchestrationError,
    ) as exc:
        print(
            "DBabel project run failed: "
            + str(exc),
            file=sys.stderr,
        )
        return 2

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

    if (
        manifest["status"]
        != "READY_FOR_HUMAN_REVIEW"
    ):
        return 2

    bundle = Path(
        manifest[
            "artifacts"
        ][
            "review_bundle"
        ][
            "path"
        ]
    ).resolve()

    output = (
        bundle.parent
        / (
            "reviewed-"
            + source.name
        )
    ).resolve()

    command = [
        sys.executable,
        str(
            ROOT
            / "scripts"
            / "start_local.py"
        ),
        "--bundle",
        str(bundle),
        "--original",
        str(source),
        "--output",
        str(output),
        "--port",
        str(
            args.workbench_port
        ),
    ]

    if args.no_browser:
        command.append(
            "--no-browser"
        )

    print(
        "",
        file=sys.stderr,
    )
    print(
        "Review bundle: {}".format(
            bundle
        ),
        file=sys.stderr,
    )
    print(
        "Native output: {}".format(
            output
        ),
        file=sys.stderr,
    )

    if not args.open_workbench:
        print(
            "Open Workbench with:",
            file=sys.stderr,
        )
        print(
            shlex.join(command),
            file=sys.stderr,
        )
        return 0

    try:
        return subprocess.call(
            command,
            cwd=str(ROOT),
        )
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run a traceable DBabel TRANSLATE project to the Full Local Workbench gate."""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import signal
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
    value.add_argument(
        "--progress-jsonl",
        type=Path,
        help="Write local, structured stage and unit progress to this file.",
    )
    value.add_argument(
        "--resume-run", type=Path,
        help="Continue a failed or interrupted run from verified batches and artifacts.",
    )
    for field in ("project-id", "vendor", "product", "product-version", "domain"):
        value.add_argument("--" + field, help="Optional translation-memory scope.")

    return value


def main() -> int:
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
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
    progress_file = None
    try:
        if args.progress_jsonl:
            progress_path = args.progress_jsonl.expanduser().resolve()
            progress_path.parent.mkdir(parents=True, exist_ok=True)
            progress_file = progress_path.open("w", encoding="utf-8")

        def report_progress(event: dict) -> None:
            if progress_file:
                progress_file.write(json.dumps(event, ensure_ascii=False) + "\n")
                progress_file.flush()

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
            on_progress=report_progress,
            resume_run=args.resume_run,
            **({"context": {key: val for key, val in {
                "project_id": args.project_id, "vendor": args.vendor, "product": args.product,
                "version": args.product_version, "domain": args.domain}.items() if val}}
               if any((args.project_id, args.vendor, args.product, args.product_version, args.domain)) else {}),
        )

    except KeyboardInterrupt:
        print("Translation interrupted; saved batches can be resumed.", file=sys.stderr)
        return 130
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
    finally:
        if progress_file:
            progress_file.close()

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

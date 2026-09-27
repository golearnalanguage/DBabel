"""Fail-closed DBabel project runtime orchestration."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterable, Optional

from runtime.audit import AuditTrail
from runtime.models import ProviderConfig
from runtime.project import (
    ProjectRun,
    atomic_write_json,
    sha256_file,
)


REPO_ROOT = Path(
    __file__
).resolve().parents[1]

SCRIPTS = REPO_ROOT / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(
        0,
        str(SCRIPTS),
    )

from prepare_runtime import (  # noqa: E402
    prepare_runtime,
)


class OrchestrationError(RuntimeError):
    pass


class RuntimeOrchestrator:
    def __init__(
        self,
        *,
        repo_root: Path = REPO_ROOT,
        workspace_root: Optional[Path] = None,
    ):
        self.repo_root = Path(
            repo_root
        ).resolve()

        self.workspace_root = Path(
            workspace_root
            or (
                self.repo_root
                / "output"
                / "runtime"
            )
        ).resolve()

    def prepare_translation(
        self,
        *,
        source: Path,
        source_language: str,
        target_language: str,
        provider_config_path: Path,
        declared_backends: Optional[
            Iterable[str]
        ] = None,
    ) -> dict:
        source = Path(source).resolve()

        if not source_language.strip():
            raise ValueError(
                "source_language is required"
            )

        if not target_language.strip():
            raise ValueError(
                "target_language is required"
            )

        if (
            source_language.strip().casefold()
            == target_language.strip().casefold()
        ):
            raise ValueError(
                "TRANSLATE requires different "
                "source and target languages"
            )

        config = ProviderConfig.from_path(
            Path(provider_config_path)
        )

        run = ProjectRun.create(
            workspace_root=self.workspace_root,
            source=source,
            mode="TRANSLATE",
            source_language=source_language,
            target_language=target_language,
            provider=config.redacted(),
        )

        audit = AuditTrail(
            run.audit_path,
            run.run_id,
        )

        try:
            source_hash_before = (
                run.assert_source_unchanged()
            )

            audit.append(
                stage="FORMAT_PROBE",
                status="STARTED",
                details={
                    "source_sha256":
                        source_hash_before,
                },
            )

            plan = prepare_runtime(
                mode="TRANSLATE",
                file_path=source,
                source_language=source_language,
                target_language=target_language,
                declared_backends=list(
                    declared_backends or []
                ),
                structured_output=True,
            )

            atomic_write_json(
                run.runtime_plan_path,
                plan,
            )

            source_hash_after = (
                run.assert_source_unchanged()
            )

            if (
                source_hash_before
                != source_hash_after
            ):
                raise OrchestrationError(
                    "source SHA changed during "
                    "runtime preparation"
                )

            runtime = plan["runtime"]
            preflight = plan.get(
                "preflight"
            ) or {}

            audit.append(
                stage="FORMAT_PROBE",
                status=(
                    "PASS"
                    if runtime["status"]
                    != "BLOCKED"
                    else "BLOCKED"
                ),
                details={
                    "runtime_status":
                        runtime["status"],
                    "preflight_status":
                        (
                            preflight.get(
                                "selection"
                            )
                            or {}
                        ).get("status"),
                },
            )

            if runtime["status"] == "BLOCKED":
                failure = {
                    "stage": "FORMAT_PROBE",
                    "reason": runtime.get(
                        "reason"
                    )
                    or "runtime preflight blocked",
                }

                run.update(
                    status="BLOCKED",
                    current_stage="FORMAT_PROBE",
                    artifacts={
                        "runtime_plan": {
                            "path": str(
                                run.runtime_plan_path
                            ),
                            "sha256": sha256_file(
                                run.runtime_plan_path
                            ),
                        }
                    },
                    failure=failure,
                )

                audit.append(
                    stage="FORMAT_PROBE",
                    status="STOPPED",
                    details=failure,
                )

                return run.load_manifest()

            selected_backend = runtime.get(
                "selected_backend"
            )

            audit.append(
                stage="CAPABILITY_PROBE",
                status="PASS",
                details={
                    "selected_backend":
                        selected_backend,
                },
            )

            context = plan[
                "task_context"
            ]

            audit.append(
                stage="TASK_CONTEXT",
                status="PASS",
                details={
                    "mode": context["mode"],
                    "format": context["format"],
                    "source_language":
                        context.get(
                            "source_language"
                        ),
                    "target_language":
                        context.get(
                            "target_language"
                        ),
                },
            )

            resource_plan = plan[
                "resource_plan"
            ]

            audit.append(
                stage="RESOURCE_ROUTING",
                status="PASS",
                details={
                    "resource_count": len(
                        resource_plan.get(
                            "resources"
                        )
                        or []
                    ),
                },
            )

            manifest = run.update(
                status="READY_FOR_INGEST",
                current_stage="RESOURCE_ROUTING",
                artifacts={
                    "runtime_plan": {
                        "path": str(
                            run.runtime_plan_path
                        ),
                        "sha256": sha256_file(
                            run.runtime_plan_path
                        ),
                    },
                    "audit_log": {
                        "path": str(
                            run.audit_path
                        ),
                    },
                },
                failure=None,
            )

            audit.append(
                stage="INGEST",
                status="READY",
                details={
                    "next_step":
                        "INGEST_VALIDATION",
                    "completion_allowed":
                        False,
                },
            )

            return manifest

        except Exception as exc:
            failure = {
                "stage": "RUNTIME_PREPARATION",
                "type": type(exc).__name__,
                "reason": str(exc),
            }

            try:
                run.update(
                    status="FAILED",
                    current_stage=
                        "RUNTIME_PREPARATION",
                    failure=failure,
                )

                audit.append(
                    stage=
                        "RUNTIME_PREPARATION",
                    status="FAILED",
                    details=failure,
                )
            finally:
                pass

            raise OrchestrationError(
                str(exc)
            ) from exc

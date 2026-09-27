"""Fail-closed DBabel project runtime orchestration."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterable, Optional

from providers.base import TextGenerationProvider
from providers.openai_compatible import (
    OpenAICompatibleProvider,
)
from runtime.audit import AuditTrail
from runtime.ingest import ingest_for_translation
from runtime.models import ProviderConfig
from runtime.post_translation import (
    prepare_post_translation,
)
from runtime.review_binding import (
    bind_review_session,
)
from runtime.semantic_adjudication import (
    SemanticLimits,
    adjudicate_semantics,
)
from runtime.translation import (
    TranslationLimits,
    translate_units,
)
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
    def run_translation_to_qa(
        self,
        *,
        source: Path,
        source_language: str,
        target_language: str,
        provider_config_path: Path,
        default_text_role: str,
        declared_backends: Optional[
            Iterable[str]
        ] = None,
        provider: Optional[
            TextGenerationProvider
        ] = None,
        limits: TranslationLimits = TranslationLimits(),
    ) -> dict:
        """Run TRANSLATE through deterministic post-translation QA.

        This method deliberately stops before semantic adjudication,
        review-session creation, human approval, or export.
        """

        manifest = self.prepare_translation(
            source=source,
            source_language=source_language,
            target_language=target_language,
            provider_config_path=
                provider_config_path,
            declared_backends=
                declared_backends,
        )

        if manifest["status"] == "BLOCKED":
            return manifest

        if (
            manifest["status"]
            != "READY_FOR_INGEST"
        ):
            raise OrchestrationError(
                "unexpected preparation state: {}".format(
                    manifest["status"]
                )
            )

        run_root = Path(
            manifest["artifacts"]
            ["runtime_plan"]["path"]
        ).parent

        run = ProjectRun(
            run_id=manifest["run_id"],
            root=run_root,
            manifest_path=
                run_root / "run.json",
            audit_path=
                run_root / "audit.jsonl",
            runtime_plan_path=
                run_root
                / "runtime-plan.json",
        )

        audit = AuditTrail(
            run.audit_path,
            run.run_id,
        )

        def artifact_record(path: Path):
            return {
                "path": str(path),
                "sha256": sha256_file(path),
            }

        stage = "INGEST"

        try:
            run.assert_source_unchanged()

            plan = json.loads(
                run.runtime_plan_path.read_text(
                    encoding="utf-8"
                )
            )

            backend = (
                plan.get("runtime")
                or {}
            ).get("selected_backend")

            if not backend:
                raise OrchestrationError(
                    "runtime plan has no selected backend"
                )

            # ---------------------------------------------
            # INGEST
            # ---------------------------------------------

            audit.append(
                stage="INGEST",
                status="STARTED",
                details={
                    "backend": backend,
                    "text_role":
                        default_text_role,
                },
            )

            ingest = ingest_for_translation(
                source=source,
                source_language=
                    source_language,
                target_language=
                    target_language,
                backend=backend,
                default_text_role=
                    default_text_role,
            )

            ingest_path = (
                run.root / "ingest.json"
            )

            atomic_write_json(
                ingest_path,
                ingest,
            )

            run.assert_source_unchanged()

            audit.append(
                stage="INGEST",
                status="PASS",
                details={
                    "ingest_status":
                        ingest[
                            "ingest_report"
                        ]["status"],
                    "units_extracted":
                        len(
                            ingest["units"]
                        ),
                },
            )

            run.update(
                status="READY_FOR_TRANSLATION",
                current_stage="INGEST",
                artifacts={
                    "ingest":
                        artifact_record(
                            ingest_path
                        ),
                },
                failure=None,
            )

            # ---------------------------------------------
            # TRANSLATION GENERATION
            # ---------------------------------------------

            stage = "TRANSLATION"

            audit.append(
                stage=stage,
                status="STARTED",
                details={
                    "unit_count":
                        len(
                            ingest["units"]
                        ),
                    "completion_allowed":
                        False,
                },
            )

            config = ProviderConfig.from_path(
                Path(
                    provider_config_path
                )
            )

            effective_provider = (
                provider
                if provider is not None
                else OpenAICompatibleProvider(
                    config
                )
            )

            translation = translate_units(
                provider=
                    effective_provider,
                units=ingest["units"],
                source_language=
                    source_language,
                target_language=
                    target_language,
                limits=limits,
            )

            translation_path = (
                run.root
                / "translation-proposals.json"
            )

            atomic_write_json(
                translation_path,
                translation,
            )

            run.assert_source_unchanged()

            audit.append(
                stage=stage,
                status="PASS",
                details={
                    "batch_count":
                        translation[
                            "batch_count"
                        ],
                    "unit_count":
                        translation[
                            "unit_count"
                        ],
                    "completion_allowed":
                        False,
                },
            )

            run.update(
                status=
                    "TRANSLATION_PROPOSED",
                current_stage=
                    "TRANSLATION",
                artifacts={
                    "translation_proposals":
                        artifact_record(
                            translation_path
                        ),
                },
                failure=None,
            )

            # ---------------------------------------------
            # POST-TRANSLATION DETERMINISTIC QA
            # ---------------------------------------------

            stage = "POST_TRANSLATION_QA"

            audit.append(
                stage=stage,
                status="STARTED",
                details={
                    "qa_target":
                        "suggested_target",
                },
            )

            post_translation = (
                prepare_post_translation(
                    translation,
                    source_language=
                        source_language,
                    target_language=
                        target_language,
                    default_text_role=
                        default_text_role,
                )
            )

            post_path = (
                run.root
                / "post-translation.json"
            )

            atomic_write_json(
                post_path,
                post_translation,
            )

            run.assert_source_unchanged()

            summary = (
                post_translation[
                    "deterministic_qa"
                ].get("summary")
                or {}
            )

            audit.append(
                stage=stage,
                status="PASS",
                details={
                    "units_checked":
                        summary.get(
                            "units_checked"
                        ),
                    "error_count":
                        summary.get(
                            "error_count"
                        ),
                    "warning_count":
                        summary.get(
                            "warning_count"
                        ),
                    "completion_allowed":
                        False,
                },
            )

            manifest = run.update(
                status=
                    "READY_FOR_SEMANTIC_ADJUDICATION",
                current_stage=
                    "POST_TRANSLATION_QA",
                artifacts={
                    "post_translation":
                        artifact_record(
                            post_path
                        ),
                },
                failure=None,
            )

            audit.append(
                stage=
                    "SEMANTIC_ADJUDICATION",
                status="READY",
                details={
                    "next_step":
                        "ADJUDICATION",
                    "completion_allowed":
                        False,
                },
            )

            return manifest

        except Exception as exc:
            failure = {
                "stage": stage,
                "type":
                    type(exc).__name__,
                "reason": str(exc),
            }

            try:
                run.update(
                    status="FAILED",
                    current_stage=stage,
                    failure=failure,
                )

                audit.append(
                    stage=stage,
                    status="FAILED",
                    details=failure,
                )
            except Exception:
                # Preserve the original execution failure
                # even if failure recording itself breaks.
                pass

            raise OrchestrationError(
                "{} failed: {}".format(
                    stage,
                    exc,
                )
            ) from exc
    def run_translation_to_review(
        self,
        *,
        source: Path,
        source_language: str,
        target_language: str,
        provider_config_path: Path,
        default_text_role: str,
        declared_backends: Optional[
            Iterable[str]
        ] = None,
        provider: Optional[
            TextGenerationProvider
        ] = None,
        translation_limits:
            TranslationLimits = TranslationLimits(),
        semantic_limits:
            SemanticLimits = SemanticLimits(),
    ) -> dict:
        """Run TRANSLATE through the Full Local Workbench delivery gate.

        A successful return means READY_FOR_HUMAN_REVIEW only.
        It does not represent human approval or workflow completion.
        """

        source = Path(
            source
        ).resolve()

        manifest = (
            self.run_translation_to_qa(
                source=source,
                source_language=
                    source_language,
                target_language=
                    target_language,
                provider_config_path=
                    provider_config_path,
                default_text_role=
                    default_text_role,
                declared_backends=
                    declared_backends,
                provider=provider,
                limits=
                    translation_limits,
            )
        )

        if (
            manifest["status"]
            == "BLOCKED"
        ):
            return manifest

        if (
            manifest["status"]
            != "READY_FOR_SEMANTIC_ADJUDICATION"
        ):
            raise OrchestrationError(
                "unexpected pre-adjudication state: {}".format(
                    manifest["status"]
                )
            )

        run_root = Path(
            manifest[
                "artifacts"
            ][
                "runtime_plan"
            ][
                "path"
            ]
        ).parent

        run = ProjectRun(
            run_id=
                manifest["run_id"],
            root=
                run_root,
            manifest_path=
                run_root
                / "run.json",
            audit_path=
                run_root
                / "audit.jsonl",
            runtime_plan_path=
                run_root
                / "runtime-plan.json",
        )

        audit = AuditTrail(
            run.audit_path,
            run.run_id,
        )

        def artifact_record(
            path: Path,
        ):
            return {
                "path":
                    str(path),
                "sha256":
                    sha256_file(
                        path
                    ),
            }

        stage = "ADJUDICATION"

        try:
            run.assert_source_unchanged()

            current = (
                run.load_manifest()
            )

            ingest_path = Path(
                current[
                    "artifacts"
                ][
                    "ingest"
                ][
                    "path"
                ]
            )

            post_path = Path(
                current[
                    "artifacts"
                ][
                    "post_translation"
                ][
                    "path"
                ]
            )

            ingest = json.loads(
                ingest_path.read_text(
                    encoding="utf-8"
                )
            )

            post_translation = (
                json.loads(
                    post_path.read_text(
                        encoding="utf-8"
                    )
                )
            )

            # ---------------------------------------------
            # SEMANTIC ADJUDICATION
            # ---------------------------------------------

            audit.append(
                stage=stage,
                status="STARTED",
                details={
                    "unit_count":
                        len(
                            post_translation[
                                "review_units"
                            ]
                        ),
                    "completion_allowed":
                        False,
                },
            )

            config = (
                ProviderConfig.from_path(
                    Path(
                        provider_config_path
                    )
                )
            )

            effective_provider = (
                provider
                if provider is not None
                else OpenAICompatibleProvider(
                    config
                )
            )

            semantic = (
                adjudicate_semantics(
                    provider=
                        effective_provider,
                    post_translation=
                        post_translation,
                    source_language=
                        source_language,
                    target_language=
                        target_language,
                    document_name=
                        source.name,
                    limits=
                        semantic_limits,
                )
            )

            semantic_path = (
                run.root
                / "semantic-adjudication.json"
            )

            atomic_write_json(
                semantic_path,
                semantic,
            )

            run.assert_source_unchanged()

            audit.append(
                stage=stage,
                status="PASS",
                details={
                    "finding_count":
                        semantic[
                            "finding_count"
                        ],
                    "unit_count":
                        semantic[
                            "unit_count"
                        ],
                    "next_state":
                        semantic[
                            "next_state"
                        ],
                    "completion_allowed":
                        False,
                },
            )

            run.update(
                status=
                    "SEMANTIC_ADJUDICATION_READY",
                current_stage=
                    "ADJUDICATION",
                artifacts={
                    "semantic_adjudication":
                        artifact_record(
                            semantic_path
                        ),
                },
                failure=None,
            )

            # ---------------------------------------------
            # REVIEW SESSION BINDING
            # ---------------------------------------------

            stage = (
                "REVIEW_SESSION_BINDING"
            )

            audit.append(
                stage=stage,
                status="STARTED",
                details={
                    "surface":
                        "FULL_LOCAL_WORKBENCH",
                    "completion_allowed":
                        False,
                },
            )

            binding = (
                bind_review_session(
                    repo_root=
                        self.repo_root,
                    run_root=
                        run.root,
                    source=
                        source,
                    source_info=
                        ingest["source"],
                    post_translation=
                        post_translation,
                    semantic_result=
                        semantic,
                    title=
                        source.name,
                )
            )

            run.assert_source_unchanged()

            audit.append(
                stage=stage,
                status="PASS",
                details={
                    "session_id":
                        binding[
                            "session_id"
                        ],
                    "surface":
                        binding[
                            "surface"
                        ],
                    "completion_allowed":
                        False,
                },
            )

            # bind_review_session already executed the
            # delivery gate; record that normative state
            # separately in the orchestration audit.
            stage = (
                "DELIVERY_VALIDATION"
            )

            receipt = binding[
                "delivery_receipt"
            ]

            audit.append(
                stage=stage,
                status="PASS",
                details={
                    "delivery_status":
                        receipt[
                            "status"
                        ],
                    "surface":
                        receipt[
                            "surface"
                        ],
                    "completion_allowed":
                        False,
                },
            )

            artifacts = dict(
                binding[
                    "artifacts"
                ]
            )

            artifacts.update({
                "semantic_adjudication":
                    artifact_record(
                        semantic_path
                    ),
                "review_bundle": {
                    "path":
                        binding[
                            "bundle_path"
                        ],
                },
                "review_session":
                    binding[
                        "session"
                    ],
            })

            manifest = run.update(
                status=
                    "READY_FOR_HUMAN_REVIEW",
                current_stage=
                    "DELIVERY_VALIDATION",
                artifacts=
                    artifacts,
                failure=None,
            )

            audit.append(
                stage="HUMAN_REVIEW",
                status="READY",
                details={
                    "session_id":
                        binding[
                            "session_id"
                        ],
                    "next_step":
                        "OPEN_FULL_LOCAL_WORKBENCH",
                    "completion_allowed":
                        False,
                },
            )

            return manifest

        except Exception as exc:
            failure = {
                "stage":
                    stage,
                "type":
                    type(exc).__name__,
                "reason":
                    str(exc),
            }

            try:
                run.update(
                    status="FAILED",
                    current_stage=
                        stage,
                    failure=
                        failure,
                )

                audit.append(
                    stage=stage,
                    status="FAILED",
                    details=
                        failure,
                )
            except Exception:
                pass

            raise OrchestrationError(
                "{} failed: {}".format(
                    stage,
                    exc,
                )
            ) from exc

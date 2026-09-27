"""Local project-run records for DBabel Runtime."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from runtime.audit import AuditTrail, utc_now


RUN_FORMAT_VERSION = "1.0"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def atomic_write_json(
    path: Path,
    value: Dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fd, temp_name = tempfile.mkstemp(
        prefix="." + path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )

    try:
        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
            newline="\n",
        ) as handle:
            json.dump(
                value,
                handle,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(
            temp_name,
            path,
        )
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


@dataclass
class ProjectRun:
    run_id: str
    root: Path
    manifest_path: Path
    audit_path: Path
    runtime_plan_path: Path

    @classmethod
    def create(
        cls,
        *,
        workspace_root: Path,
        source: Path,
        mode: str,
        source_language: str,
        target_language: str,
        provider: Optional[Dict[str, Any]] = None,
    ) -> "ProjectRun":
        source = Path(source).resolve()

        if not source.is_file():
            raise ValueError(
                "source file not found: {}".format(source)
            )

        workspace_root = Path(
            workspace_root
        ).resolve()

        workspace_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        run_id = "RUN_" + uuid.uuid4().hex

        run_root = workspace_root / run_id
        run_root.mkdir(
            mode=0o700,
            parents=False,
            exist_ok=False,
        )

        try:
            os.chmod(
                run_root,
                0o700,
            )
        except OSError:
            pass

        run = cls(
            run_id=run_id,
            root=run_root,
            manifest_path=run_root / "run.json",
            audit_path=run_root / "audit.jsonl",
            runtime_plan_path=run_root
            / "runtime-plan.json",
        )

        source_hash = sha256_file(source)

        manifest = {
            "format_version": RUN_FORMAT_VERSION,
            "run_id": run_id,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "mode": mode,
            "source_language": source_language,
            "target_language": target_language,
            "status": "CREATED",
            "current_stage": "INTAKE",
            "completion_allowed": False,
            "source": {
                "path": str(source),
                "filename": source.name,
                "size_bytes": source.stat().st_size,
                "sha256": source_hash,
            },
            "provider": provider or None,
            "artifacts": {},
            "failure": None,
        }

        atomic_write_json(
            run.manifest_path,
            manifest,
        )

        AuditTrail(
            run.audit_path,
            run_id,
        ).append(
            stage="INTAKE",
            status="CREATED",
            details={
                "source_filename": source.name,
                "source_sha256": source_hash,
                "mode": mode,
            },
        )

        return run

    def load_manifest(self) -> Dict[str, Any]:
        value = json.loads(
            self.manifest_path.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(value, dict):
            raise ValueError(
                "run manifest root must be an object"
            )

        if value.get("run_id") != self.run_id:
            raise ValueError(
                "run manifest run_id mismatch"
            )

        return value

    def update(
        self,
        *,
        status: str,
        current_stage: str,
        artifacts: Optional[Dict[str, Any]] = None,
        failure: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        manifest = self.load_manifest()

        manifest["status"] = status
        manifest["current_stage"] = current_stage
        manifest["updated_at"] = utc_now()
        manifest["completion_allowed"] = False

        if artifacts:
            existing = dict(
                manifest.get("artifacts")
                or {}
            )
            existing.update(artifacts)
            manifest["artifacts"] = existing

        manifest["failure"] = failure

        atomic_write_json(
            self.manifest_path,
            manifest,
        )

        return manifest

    def assert_source_unchanged(self) -> str:
        manifest = self.load_manifest()
        source = Path(
            manifest["source"]["path"]
        )

        if not source.is_file():
            raise ValueError(
                "source file disappeared during runtime"
            )

        current = sha256_file(source)
        expected = manifest["source"]["sha256"]

        if current != expected:
            raise ValueError(
                "source file changed during runtime"
            )

        return current

"""Process-held run locks. A persistent file avoids inode replacement races."""
from __future__ import annotations

import json
import os
from pathlib import Path
import uuid


class RunBusyError(RuntimeError):
    pass


def _lock(handle):
    handle.seek(0)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(handle):
    handle.seek(0)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def probe_run_liveness(root: Path) -> str:
    """Missing/invalid legacy ownership information is explicitly unknown."""
    path = Path(root) / ".run-lease"
    try:
        with path.open("r+b") as handle:
            handle.seek(1)
            record = json.load(handle)
            if record.get("protocol") != "dbabel-run-lease-1":
                return "UNKNOWN"
            try:
                _lock(handle)
            except BlockingIOError:
                return "ACTIVE"
            except OSError:
                return "UNKNOWN"
            _unlock(handle)
            return "INACTIVE"
    except (OSError, ValueError, AttributeError):
        return "UNKNOWN"


class RunLease:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.handle = None

    def __enter__(self):
        handle = (self.root / ".run-lease").open("a+b")
        try:
            if handle.seek(0, 2) == 0:
                handle.write(b"\0")
                handle.flush()
            try:
                _lock(handle)
            except OSError as exc:
                raise RunBusyError("run is active or its ownership lock is unavailable") from exc
            handle.seek(1)
            handle.truncate()
            record = {"protocol": "dbabel-run-lease-1", "pid": os.getpid(),
                      "owner_token": uuid.uuid4().hex}
            handle.write(json.dumps(record).encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
            self.handle = handle
            return self
        except BaseException:
            handle.close()
            raise

    def __exit__(self, *unused):
        if self.handle is not None:
            try:
                _unlock(self.handle)
            finally:
                self.handle.close()
                self.handle = None


RESUMABLE_STATES = {"FAILED", "INTERRUPTED", "READY_FOR_TRANSLATION",
                    "TRANSLATION_PROPOSED", "READY_FOR_SEMANTIC_ADJUDICATION",
                    "SEMANTIC_ADJUDICATED"}


def resumable_runs(workspace: Path):
    """Read-only discovery; resume rechecks ownership and artifact identities."""
    rows = []
    for path in Path(workspace).glob("RUN_*/run.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            status = value.get("status")
            if (value.get("mode") != "TRANSLATE" or status not in RESUMABLE_STATES
                    or not (value.get("artifacts") or {}).get("ingest")):
                continue
            live = probe_run_liveness(path.parent)
            if live == "ACTIVE" or (status not in {"FAILED", "INTERRUPTED"} and live != "INACTIVE"):
                continue
            source = value.get("source") or {}
            if not Path(source.get("path", "")).is_file():
                continue
            rows.append({"root": str(path.parent), "source": source["path"],
                         "source_language": value["source_language"],
                         "target_language": value["target_language"],
                         "provider": value["provider"], "status": status,
                         "liveness": live, "updated_at": value.get("updated_at", "")})
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return sorted(rows, key=lambda row: row["updated_at"], reverse=True)

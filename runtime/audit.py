"""Append-only hash-chained audit events for DBabel Runtime."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


FORMAT_VERSION = "1.0"
ZERO_HASH = "0" * 64

_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "credential",
    "credentials",
}


class AuditError(RuntimeError):
    pass


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            normalized = str(key).casefold()
            if normalized in _SENSITIVE_KEYS:
                result[key] = "<redacted>"
            else:
                result[key] = redact_sensitive(item)
        return result

    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]

    if isinstance(value, tuple):
        return [redact_sensitive(item) for item in value]

    return value


def event_hash(event_without_hash: Dict[str, Any]) -> str:
    return hashlib.sha256(
        canonical_json(event_without_hash)
    ).hexdigest()


def read_events(path: Path) -> list:
    if not path.exists():
        return []

    events = []
    with path.open(
        "r",
        encoding="utf-8",
    ) as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue

            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise AuditError(
                    "invalid audit JSON at line {}".format(
                        line_number
                    )
                ) from exc

            if not isinstance(value, dict):
                raise AuditError(
                    "audit event at line {} is not an object".format(
                        line_number
                    )
                )

            events.append(value)

    return events


def verify_events(
    events: Iterable[Dict[str, Any]],
    expected_run_id: Optional[str] = None,
) -> Dict[str, Any]:
    previous = ZERO_HASH
    count = 0
    run_id = expected_run_id

    for expected_sequence, event in enumerate(
        events,
        1,
    ):
        count += 1

        if event.get("format_version") != FORMAT_VERSION:
            raise AuditError(
                "unsupported audit format version"
            )

        current_run_id = event.get("run_id")
        if not isinstance(current_run_id, str) or not current_run_id:
            raise AuditError("audit event has no run_id")

        if run_id is None:
            run_id = current_run_id

        if current_run_id != run_id:
            raise AuditError(
                "audit run_id changed inside one chain"
            )

        if event.get("sequence") != expected_sequence:
            raise AuditError(
                "audit sequence mismatch at event {}".format(
                    expected_sequence
                )
            )

        if event.get("previous_hash") != previous:
            raise AuditError(
                "audit previous_hash mismatch at event {}".format(
                    expected_sequence
                )
            )

        actual_hash = event.get("event_hash")
        if not isinstance(actual_hash, str):
            raise AuditError(
                "audit event_hash missing at event {}".format(
                    expected_sequence
                )
            )

        body = dict(event)
        body.pop("event_hash", None)

        expected_hash = event_hash(body)

        if actual_hash != expected_hash:
            raise AuditError(
                "audit event hash mismatch at event {}".format(
                    expected_sequence
                )
            )

        previous = actual_hash

    return {
        "valid": True,
        "event_count": count,
        "run_id": run_id,
        "head_hash": previous,
    }


def verify_file(
    path: Path,
    expected_run_id: Optional[str] = None,
) -> Dict[str, Any]:
    return verify_events(
        read_events(path),
        expected_run_id=expected_run_id,
    )


class AuditTrail:
    def __init__(
        self,
        path: Path,
        run_id: str,
    ):
        self.path = Path(path)
        self.run_id = str(run_id)

        if not self.run_id:
            raise ValueError("run_id is required")

    def append(
        self,
        *,
        stage: str,
        status: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        events = read_events(self.path)

        if events:
            verification = verify_events(
                events,
                expected_run_id=self.run_id,
            )
            sequence = verification["event_count"] + 1
            previous_hash = verification["head_hash"]
        else:
            sequence = 1
            previous_hash = ZERO_HASH

        body = {
            "format_version": FORMAT_VERSION,
            "run_id": self.run_id,
            "sequence": sequence,
            "timestamp": utc_now(),
            "stage": str(stage),
            "status": str(status),
            "previous_hash": previous_hash,
            "details": redact_sensitive(
                details or {}
            ),
        }

        event = dict(body)
        event["event_hash"] = event_hash(body)

        encoded = (
            json.dumps(
                event,
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")

        fd = os.open(
            str(self.path),
            os.O_WRONLY
            | os.O_CREAT
            | os.O_APPEND,
            0o600,
        )

        try:
            with os.fdopen(fd, "ab") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            raise

        verify_file(
            self.path,
            expected_run_id=self.run_id,
        )

        return event

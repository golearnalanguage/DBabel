#!/usr/bin/env python3
"""Import decisions exported by DBabel Portable Review into a .dbreview bundle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from review_model import (
    append_event,
    load_bundle,
    normalize_decision,
    save_decisions,
    utc_now,
)


def _load_portable_payload(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(
            "portable decision file must be an object containing session_id and "
            "decisions; legacy bare decision arrays are not safe to import"
        )

    session_id = payload.get("session_id")
    rows = payload.get("decisions")

    if not isinstance(session_id, str) or not session_id:
        raise ValueError("portable decision file requires non-empty session_id")
    if not isinstance(rows, list):
        raise ValueError("portable decision file requires decisions array")

    return payload, rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("bundle")
    p.add_argument("decisions")
    a = p.parse_args()

    bundle = Path(a.bundle)
    data = load_bundle(bundle)

    try:
        payload, rows = _load_portable_payload(Path(a.decisions))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        p.error(str(exc))

    if payload["session_id"] != data["session"]["session_id"]:
        p.error("decision file belongs to a different review session")

    incoming = {}
    for row in rows:
        if not isinstance(row, dict):
            p.error("portable decisions must contain objects only")

        uid = row.get("unit_id")
        if not isinstance(uid, str) or not uid:
            p.error("portable decision is missing unit_id")

        if uid in incoming:
            p.error("portable decision file contains duplicate unit_id: " + uid)

        incoming[uid] = row

    expected = set(data["units_by_id"])
    actual = set(incoming)

    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        message = "portable decision coverage does not match review session"
        if missing:
            message += "; missing=" + ",".join(missing)
        if extra:
            message += "; extra=" + ",".join(extra)
        p.error(message)

    saved = []

    for unit in data["units"]:
        uid = unit["id"]
        previous = data["decisions_by_id"][uid]
        incoming_row = incoming[uid]

        # Portable revision is transport evidence only. normalize_decision
        # increments the local revision and invalidates QA so imported edits
        # must receive a fresh local recheck before native export.
        current = normalize_decision(unit, incoming_row, previous)
        saved.append(current)

        if (
            current["status"] != previous["status"]
            or current.get("approved_target")
            != previous.get("approved_target")
        ):
            append_event(
                bundle / "events.jsonl",
                {
                    "event": "DECISION_CHANGED",
                    "unit_id": uid,
                    "at": utc_now(),
                    "revision": current["revision"],
                    "actor": "HUMAN",
                    "from_status": previous["status"],
                    "to_status": current["status"],
                    "detail": "Imported from portable review",
                },
            )

    save_decisions(bundle, saved)
    print("Imported {} decisions".format(len(saved)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

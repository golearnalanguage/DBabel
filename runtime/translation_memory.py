"""Local, indexed translation memory. Human decisions only; no model calls."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from typing import Any, Dict, Optional, Sequence


def database_path() -> Path:
    override = os.environ.get("DBABEL_TRANSLATION_MEMORY")
    if override:
        return Path(override).expanduser()
    base = (Path.home() / "Library/Application Support/DBabel" if sys.platform == "darwin"
            else Path.home() / ".dbabel")
    return base / "translation-memory.sqlite3"


def _key(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _role(unit: Dict[str, Any]) -> str:
    return str(unit.get("text_role") or (unit.get("context") or {}).get("text_role") or "PROSE")


def _connect() -> sqlite3.Connection:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("""CREATE TABLE IF NOT EXISTS memories (
        source_language TEXT NOT NULL, target_language TEXT NOT NULL,
        text_role TEXT NOT NULL, source_hash TEXT NOT NULL, source TEXT NOT NULL,
        kind TEXT NOT NULL CHECK(kind IN ('PREFERRED','REJECTED')),
        target TEXT NOT NULL, decision TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(source_language,target_language,text_role,source_hash,kind,target)
    )""")
    connection.execute("""CREATE INDEX IF NOT EXISTS memories_lookup ON memories
        (source_language,target_language,text_role,source_hash,kind)""")
    return connection


def remember(unit: Dict[str, Any], decision: Dict[str, Any]) -> None:
    """Persist an already-saved human choice; later choices supersede earlier ones."""
    status = str(decision.get("status") or "")
    if status not in {"ACCEPT_SUGGESTION", "KEEP_CURRENT", "USER_EDITED", "BLOCKED"}:
        return
    source = str(unit.get("source") or "")
    source_language = str(unit.get("source_language") or "")
    target_language = str(unit.get("target_language") or "")
    target = str(unit.get("suggested_target") or "") if status == "BLOCKED" else str(decision.get("approved_target") or "")
    if not source.strip() or not target.strip() or not source_language or not target_language:
        return
    kind = "REJECTED" if status == "BLOCKED" else "PREFERRED"
    fields = (source_language, target_language, _role(unit), _key(source))
    with _connect() as db:
        if kind == "PREFERRED":
            db.execute("""DELETE FROM memories WHERE source_language=? AND target_language=?
                AND text_role=? AND source_hash=? AND kind='PREFERRED'""", fields)
        db.execute("""INSERT INTO memories
            (source_language,target_language,text_role,source_hash,source,kind,target,decision)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(source_language,target_language,text_role,source_hash,kind,target)
            DO UPDATE SET decision=excluded.decision, updated_at=CURRENT_TIMESTAMP""",
            (*fields, source, kind, target, status))


def match(unit: Dict[str, Any], source_language: str, target_language: str) -> Optional[str]:
    """Indexed exact match only. Rejects take precedence over an obsolete preference."""
    source = str(unit.get("source") or "")
    if not source or not database_path().exists():
        return None
    with _connect() as db:
        rows = db.execute("""SELECT source,kind,target FROM memories WHERE
            source_language=? AND target_language=? AND text_role=? AND source_hash=?""",
            (source_language, target_language, _role(unit), _key(source))).fetchall()
    preferred = {row["target"] for row in rows if row["source"] == source and row["kind"] == "PREFERRED"}
    rejected = {row["target"] for row in rows if row["source"] == source and row["kind"] == "REJECTED"}
    usable = preferred - rejected
    return next(iter(usable)) if len(usable) == 1 else None


def matches(units: Sequence[Dict[str, Any]], source_language: str,
            target_language: str) -> Dict[str, str]:
    """Fetch all indexed exact matches with one connection; no remote request."""
    if not database_path().exists() or not units:
        return {}
    keys = {(str(unit.get("source") or ""), _role(unit)) for unit in units
            if str(unit.get("source") or "")}
    hashes = list({_key(source) for source, _ in keys})
    rows = []
    with _connect() as db:
        for start in range(0, len(hashes), 400):
            chunk = hashes[start:start + 400]
            rows.extend(db.execute("""SELECT source,text_role,kind,target FROM memories
                WHERE source_language=? AND target_language=? AND source_hash IN ({})""".format(
                    ",".join("?" for _ in chunk)), (source_language, target_language, *chunk)).fetchall())
    by_key = {}
    for row in rows:
        item = by_key.setdefault((row["source"], row["text_role"]), {"PREFERRED": set(), "REJECTED": set()})
        item[row["kind"]].add(row["target"])
    result = {}
    for unit in units:
        item = by_key.get((str(unit.get("source") or ""), _role(unit)))
        if not item:
            continue
        usable = item["PREFERRED"] - item["REJECTED"]
        if len(usable) == 1:
            result[unit["id"]] = next(iter(usable))
    return result


def rejections() -> list[Dict[str, str]]:
    if not database_path().exists():
        return []
    with _connect() as db:
        rows = db.execute("""SELECT source_language,target_language,source,target FROM memories
            WHERE kind='REJECTED'""").fetchall()
    return [{"source_language": row["source_language"], "target_language": row["target_language"],
             "source": row["source"], "rejected_target": row["target"], "scope": "SEGMENT"}
            for row in rows]


def forget_rejection(record: Dict[str, str]) -> None:
    if not database_path().exists():
        return
    with _connect() as db:
        db.execute("""DELETE FROM memories WHERE source_language=? AND target_language=?
            AND source_hash=? AND source=? AND kind='REJECTED' AND target=?""",
            (record.get("source_language", ""), record.get("target_language", ""),
             _key(record.get("source", "")), record.get("source", ""),
             record.get("rejected_target", "")))


def summary(limit: int = 20) -> Dict[str, Any]:
    if not database_path().exists():
        return {"count": 0, "entries": []}
    with _connect() as db:
        count = db.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        rows = db.execute("""SELECT rowid AS id,source_language,target_language,text_role,source,kind,target,decision,updated_at
            FROM memories ORDER BY updated_at DESC LIMIT ?""", (limit,)).fetchall()
    return {"count": count, "entries": [dict(row) for row in rows]}


def export_entries() -> list[Dict[str, Any]]:
    if not database_path().exists():
        return []
    with _connect() as db:
        rows = db.execute("""SELECT source_language,target_language,text_role,source,kind,target,decision,updated_at
            FROM memories ORDER BY source_language,target_language,source,text_role,kind,target""").fetchall()
    return [dict(row) for row in rows]


def edit_entry(entry_id: int, target: str) -> None:
    if type(entry_id) is not int or entry_id < 1 or not target.strip() or len(target) > 20000:
        raise ValueError("invalid translation memory edit")
    with _connect() as db:
        row = db.execute("SELECT kind,source_language,target_language,text_role,source_hash FROM memories WHERE rowid=?",
                         (entry_id,)).fetchone()
        if row is None:
            raise ValueError("translation memory entry not found")
        if row["kind"] == "PREFERRED":
            forbidden = db.execute("""SELECT 1 FROM memories WHERE source_language=? AND target_language=?
                AND text_role=? AND source_hash=? AND kind='REJECTED' AND target=?""",
                (row["source_language"], row["target_language"], row["text_role"], row["source_hash"], target)).fetchone()
            if forbidden:
                raise ValueError("this wording was rejected for the same source")
        db.execute("""UPDATE memories SET target=?,decision='USER_EDITED_MEMORY',updated_at=CURRENT_TIMESTAMP
            WHERE rowid=?""", (target, entry_id))


def delete_entry(entry_id: int) -> None:
    if type(entry_id) is not int or entry_id < 1:
        raise ValueError("invalid translation memory entry id")
    with _connect() as db:
        cursor = db.execute("DELETE FROM memories WHERE rowid=?", (entry_id,))
        if cursor.rowcount != 1:
            raise ValueError("translation memory entry not found")


def backup() -> Path:
    """Create a consistent, replace-on-success snapshot after review actions."""
    source = database_path()
    if not source.exists():
        return source
    destination = source.with_name(source.stem + ".backup" + source.suffix)
    descriptor, temporary = tempfile.mkstemp(prefix=".translation-memory-", suffix=".sqlite3",
                                            dir=source.parent)
    os.close(descriptor)
    try:
        with sqlite3.connect(source, timeout=10) as origin, sqlite3.connect(temporary) as snapshot:
            origin.backup(snapshot)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return destination

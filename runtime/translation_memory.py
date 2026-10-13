"""Local, indexed translation memory. Human decisions only; no model calls."""
from __future__ import annotations

from contextlib import closing, contextmanager
from difflib import SequenceMatcher
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from typing import Any, Dict, Iterator, Optional, Sequence

from runtime.memory_scope import canonical_scope


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


_TABLE_SQL = """CREATE TABLE {name} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope_key TEXT NOT NULL, scope_kind TEXT NOT NULL, scope_json TEXT NOT NULL,
    source_language TEXT NOT NULL, target_language TEXT NOT NULL,
    text_role TEXT NOT NULL, source_hash TEXT NOT NULL, source TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('PREFERRED','REJECTED')),
    target TEXT NOT NULL, decision TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(scope_key,source_language,target_language,text_role,source_hash,kind,target)
)"""


def _initialize(db: sqlite3.Connection, path: Path) -> None:
    columns = {row["name"] for row in db.execute("PRAGMA table_info(memories)")}
    if "scope_key" in columns and db.execute("PRAGMA user_version").fetchone()[0] == 2:
        return
    if columns and "scope_key" not in columns:
        # Preserve a consistent pre-migration snapshot, including committed WAL
        # data. Migration never turns a missing historic scope into global scope.
        destination = path.with_name(path.stem + ".pre-scope-v1" + path.suffix)
        if not destination.exists():
            _snapshot(path, destination)
    db.execute("BEGIN IMMEDIATE")
    try:
        columns = {row["name"] for row in db.execute("PRAGMA table_info(memories)")}
        if not columns:
            db.execute(_TABLE_SQL.format(name="memories"))
        elif "scope_key" not in columns:
            rows = db.execute("SELECT rowid AS id,* FROM memories").fetchall()
            db.execute(_TABLE_SQL.format(name="memories_scoped_v2"))
            for row in rows:
                scope = canonical_scope({"text_role": row["text_role"]})
                db.execute("""INSERT INTO memories_scoped_v2
                    (id,scope_key,scope_kind,scope_json,source_language,target_language,
                     text_role,source_hash,source,kind,target,decision,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (row["id"], scope["key"], "LEGACY_UNSCOPED", json.dumps(scope["context"], sort_keys=True),
                     row["source_language"], row["target_language"], row["text_role"],
                     row["source_hash"], row["source"], row["kind"], row["target"],
                     row["decision"], row["updated_at"]))
            db.execute("DROP TABLE memories")
            db.execute("ALTER TABLE memories_scoped_v2 RENAME TO memories")
        db.execute("""CREATE INDEX IF NOT EXISTS memories_lookup_v2 ON memories
            (scope_key,source_language,target_language,text_role,source_hash,kind)""")
        db.execute("PRAGMA user_version=2")
        db.commit()
    except Exception:
        db.rollback()
        raise


def _snapshot(source: Path, destination: Path) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=".translation-memory-", suffix=".sqlite3",
                                            dir=source.parent)
    os.close(descriptor)
    try:
        with closing(sqlite3.connect(source, timeout=10)) as origin, closing(sqlite3.connect(temporary)) as target:
            origin.backup(target)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _scope_fields(scope: Dict[str, Any]) -> tuple:
    return scope["key"], scope["kind"], json.dumps(scope["context"], ensure_ascii=False, sort_keys=True)


def _row_scope(row: sqlite3.Row) -> Dict[str, Any]:
    scope = canonical_scope({"context": json.loads(row["scope_json"])})
    if scope["key"] != row["scope_key"] or scope["kind"] != row["scope_kind"]:
        raise ValueError("translation memory scope identity is invalid")
    return scope


def _entry(row: sqlite3.Row) -> Dict[str, Any]:
    result = dict(row)
    result["scope"] = _row_scope(row)
    for field in ("scope_key", "scope_kind", "scope_json", "source_hash"):
        result.pop(field, None)
    return result


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        _initialize(connection, path)
        with connection:
            yield connection
    finally:
        connection.close()


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
    scope = canonical_scope(unit)
    fields = (scope["key"], source_language, target_language, _role(unit), _key(source))
    with _connect() as db:
        if kind == "PREFERRED":
            db.execute("""DELETE FROM memories WHERE scope_key=? AND source_language=? AND target_language=?
                AND text_role=? AND source_hash=? AND kind='PREFERRED'""", fields)
        db.execute("""INSERT INTO memories
            (scope_key,scope_kind,scope_json,source_language,target_language,text_role,source_hash,source,kind,target,decision)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(scope_key,source_language,target_language,text_role,source_hash,kind,target)
            DO UPDATE SET decision=excluded.decision, updated_at=CURRENT_TIMESTAMP""",
            (*_scope_fields(scope), source_language, target_language, _role(unit),
             _key(source), source, kind, target, status))


def match(unit: Dict[str, Any], source_language: str, target_language: str) -> Optional[str]:
    """Indexed exact match only. Rejects take precedence over an obsolete preference."""
    selected = dict(unit, id="match")
    return matches([selected], source_language, target_language).get("match")


def matches(units: Sequence[Dict[str, Any]], source_language: str,
            target_language: str) -> Dict[str, str]:
    """Fetch all indexed exact matches with one connection; no remote request."""
    if not database_path().exists() or not units:
        return {}
    groups: Dict[str, set] = {}
    for unit in units:
        scope = canonical_scope(unit)
        if scope["automatic"] and unit.get("source"):
            groups.setdefault(scope["key"], set()).add(_key(str(unit["source"])))
    if not groups:
        return {}
    rows = []
    with _connect() as db:
        for scope_key, selected_hashes in groups.items():
            hashes = sorted(selected_hashes)
            for start in range(0, len(hashes), 400):
                chunk = hashes[start:start + 400]
                rows.extend(db.execute("""SELECT * FROM memories
                    WHERE scope_key=? AND source_language=? AND target_language=? AND source_hash IN ({})""".format(
                        ",".join("?" for _ in chunk)), (scope_key, source_language, target_language, *chunk)).fetchall())
    by_key = {}
    for row in rows:
        scope = _row_scope(row)
        item = by_key.setdefault((scope["key"], row["source"]), {"PREFERRED": set(), "REJECTED": set()})
        item[row["kind"]].add(row["target"])
    result = {}
    for unit in units:
        scope = canonical_scope(unit)
        item = by_key.get((scope["key"], str(unit.get("source") or ""))) if scope["automatic"] else None
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
        rows = db.execute("""SELECT * FROM memories
            WHERE kind='REJECTED'""").fetchall()
    return [{"source_language": row["source_language"], "target_language": row["target_language"],
             "source": row["source"], "rejected_target": row["target"], "scope": "SEGMENT",
             "memory_scope": _row_scope(row)}
            for row in rows]


def forget_rejection(record: Dict[str, str]) -> None:
    if not database_path().exists():
        return
    scope = record.get("memory_scope")
    if not isinstance(scope, dict):
        return
    canonical = canonical_scope({"context": scope.get("context")})
    if canonical["key"] != scope.get("key"):
        raise ValueError("rejection scope identity is invalid")
    with _connect() as db:
        db.execute("""DELETE FROM memories WHERE scope_key=? AND source_language=? AND target_language=?
            AND source_hash=? AND source=? AND kind='REJECTED' AND target=?""",
            (canonical["key"], record.get("source_language", ""), record.get("target_language", ""),
             _key(record.get("source", "")), record.get("source", ""),
             record.get("rejected_target", "")))


def summary(limit: int = 20) -> Dict[str, Any]:
    if not database_path().exists():
        return {"count": 0, "entries": []}
    with _connect() as db:
        count = db.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        rows = db.execute("SELECT * FROM memories ORDER BY updated_at DESC,id DESC LIMIT ?", (limit,)).fetchall()
    return {"count": count, "entries": [_entry(row) for row in rows]}


def export_entries() -> list[Dict[str, Any]]:
    if not database_path().exists():
        return []
    with _connect() as db:
        rows = db.execute("""SELECT * FROM memories ORDER BY
            scope_key,source_language,target_language,source,text_role,kind,target""").fetchall()
    return [_entry(row) for row in rows]


def edit_entry(entry_id: int, target: str) -> None:
    if type(entry_id) is not int or entry_id < 1 or not target.strip() or len(target) > 20000:
        raise ValueError("invalid translation memory edit")
    with _connect() as db:
        row = db.execute("SELECT * FROM memories WHERE id=?",
                         (entry_id,)).fetchone()
        if row is None:
            raise ValueError("translation memory entry not found")
        if row["kind"] == "PREFERRED":
            forbidden = db.execute("""SELECT 1 FROM memories WHERE scope_key=? AND source_language=? AND target_language=?
                AND text_role=? AND source_hash=? AND kind='REJECTED' AND target=?""",
                (row["scope_key"], row["source_language"], row["target_language"], row["text_role"], row["source_hash"], target)).fetchone()
            if forbidden:
                raise ValueError("this wording was rejected for the same source")
        db.execute("""UPDATE memories SET target=?,decision='USER_EDITED_MEMORY',updated_at=CURRENT_TIMESTAMP
            WHERE id=?""", (target, entry_id))


def delete_entry(entry_id: int) -> None:
    if type(entry_id) is not int or entry_id < 1:
        raise ValueError("invalid translation memory entry id")
    with _connect() as db:
        cursor = db.execute("DELETE FROM memories WHERE id=?", (entry_id,))
        if cursor.rowcount != 1:
            raise ValueError("translation memory entry not found")


def backup() -> Path:
    """Create a consistent, replace-on-success snapshot after review actions."""
    source = database_path()
    if not source.exists():
        return source
    destination = source.with_name(source.stem + ".backup" + source.suffix)
    _snapshot(source, destination)
    return destination


def similar_candidates(unit: Dict[str, Any], source_language: str, target_language: str,
                       *, limit: int = 5, score_cutoff: float = 70) -> Dict[str, Any]:
    """Rank scope-filtered human memory as suggestions, without changing a unit."""
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError("candidate limit must be an integer from 1 to 20")
    if isinstance(score_cutoff, bool) or not isinstance(score_cutoff, (int, float)) or not 0 <= score_cutoff <= 100:
        raise ValueError("candidate score cutoff must be from 0 to 100")
    scope = canonical_scope(unit)
    result = {"available": True, "reason": None, "authority": "SUGGESTION_ONLY",
              "scope": scope, "candidates": []}
    if not scope["automatic"]:
        return dict(result, available=False, reason="scope_unavailable")
    try:
        from rapidfuzz.fuzz import ratio
    except ImportError:
        return dict(result, available=False, reason="rapidfuzz_not_installed")
    if not database_path().exists():
        return result
    with _connect() as db:
        rows = db.execute("""SELECT * FROM memories WHERE scope_key=?
            AND source_language=? AND target_language=? ORDER BY id""",
            (scope["key"], source_language, target_language)).fetchall()
    rejected = {(row["source"], row["target"]) for row in rows if row["kind"] == "REJECTED"}
    query = str(unit.get("source") or "")
    candidates = []
    for row in rows:
        if row["kind"] != "PREFERRED" or (row["source"], row["target"]) in rejected:
            continue
        row_scope = _row_scope(row)
        score = ratio(row["source"], query, score_cutoff=score_cutoff)
        if score < score_cutoff:
            continue
        differences = [{"operation": tag, "source_start": a, "source_end": b,
                        "query_start": c, "query_end": d, "before": row["source"][a:b], "after": query[c:d]}
                       for tag, a, b, c, d in SequenceMatcher(None, row["source"], query, autojunk=False).get_opcodes()
                       if tag != "equal"]
        candidates.append({"id": row["id"], "source": row["source"], "target": row["target"],
                           "score": round(float(score), 2), "scope": row_scope,
                           "authority": "SUGGESTION_ONLY", "differences": differences})
    result["candidates"] = sorted(candidates, key=lambda item: (-item["score"], item["id"]))[:limit]
    return result

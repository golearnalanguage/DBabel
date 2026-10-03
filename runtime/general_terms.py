"""Opt-in, cross-vendor database terminology references for AI proposals.

These entries never become project-approved glossary decisions.
"""
from __future__ import annotations

from functools import lru_cache
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def catalog() -> Dict[str, object]:
    data = json.loads((ROOT / "config/general_database_terms.json").read_text(encoding="utf-8"))
    if data.get("status") != "REFERENCE_ONLY_NOT_PROJECT_APPROVED":
        raise ValueError("general database terms must remain reference-only")
    return data


def settings_path() -> Path:
    override = os.environ.get("DBABEL_GENERAL_TERMS_SETTINGS")
    if override:
        return Path(override).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/DBabel/general-terms-settings.json"
    return Path.home() / ".dbabel/general-terms-settings.json"


def enabled() -> bool:
    try:
        value = json.loads(settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(value, dict) and value.get("enabled") is True


def set_enabled(value: bool) -> None:
    if type(value) is not bool:
        raise ValueError("enabled must be a boolean")
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp = tempfile.mkstemp(prefix=".general-terms-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump({"enabled": value}, stream)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def candidates(source: str, source_language: str, target_language: str) -> List[Dict[str, str]]:
    if not enabled() or (source_language, target_language) != ("zh-CN", "en"):
        return []
    return [{"source": item["zh"], "suggested_target": item["en"]}
            for item in catalog()["entries"]
            if item["zh"] == source.strip() or
            (len(item["zh"]) > 1 and item["zh"] in source)][:16]

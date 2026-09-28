"""Durable, input-bound checkpoints for provider batches."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from runtime.project import atomic_write_json


def checkpoint_digest(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_checkpoint(
    path: Path,
    *,
    stage: str,
    input_digest: str,
    expected_ids: Sequence[str],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if not path.exists():
        return [], []
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("format_version") != "1.0":
        raise ValueError("invalid batch checkpoint")
    if value.get("stage") != stage or value.get("input_digest") != input_digest:
        raise ValueError("batch checkpoint does not match the current run")
    items = value.get("items")
    receipts = value.get("receipts")
    if not isinstance(items, list) or not isinstance(receipts, list):
        raise ValueError("invalid batch checkpoint contents")
    ids = [item.get("id") for item in items if isinstance(item, dict)]
    if len(ids) != len(items) or ids != list(expected_ids[:len(ids)]):
        raise ValueError("batch checkpoint unit sequence mismatch")
    receipt_ids = []
    for index, receipt in enumerate(receipts, 1):
        if not isinstance(receipt, dict) or receipt.get("batch_index") != index:
            raise ValueError("batch checkpoint receipt sequence mismatch")
        unit_ids = receipt.get("unit_ids")
        if not isinstance(unit_ids, list) or not unit_ids:
            raise ValueError("invalid batch checkpoint receipt")
        receipt_ids.extend(unit_ids)
    if receipt_ids != ids:
        raise ValueError("batch checkpoint receipts do not match saved units")
    return items, receipts


def save_checkpoint(
    path: Path,
    *,
    stage: str,
    input_digest: str,
    items: List[Dict[str, Any]],
    receipts: List[Dict[str, Any]],
) -> None:
    atomic_write_json(path, {
        "format_version": "1.0",
        "stage": stage,
        "input_digest": input_digest,
        "items": items,
        "receipts": receipts,
    })

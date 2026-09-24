#!/usr/bin/env python3
"""Extract auditable bilingual units from source and target DOCX files.

Default behavior remains strict positional alignment: source and target must
contain the same number of non-empty paragraphs.

For real documents with split, merged, unaligned, or uncertain paragraphs,
--alignment-map accepts an explicit JSON alignment map. DBabel never guesses
those mappings. Every non-empty source and target paragraph must be covered
exactly once, and duplicate or missing coverage fails closed.

Alignment-map paragraph indexes are 1-based positions in the extracted
non-empty paragraph sequence.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence, Set

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from docx_review_adapter import extract_paragraphs
from review_model import write_jsonl


ALIGNMENT_STATUSES = {
    "ALIGNED",
    "AMBIGUOUS",
    "SPLIT",
    "MERGED",
    "UNALIGNED",
}


def _paragraph_ref(row: Dict[str, Any]) -> str:
    return "docx:{}:p={}".format(
        row["part"],
        row["paragraph_ordinal"],
    )


def _normalize_indexes(
    value: Any,
    field: str,
    alignment_id: str,
    count: int,
) -> List[int]:
    if not isinstance(value, list):
        raise ValueError(
            "{} {} must be an array".format(
                alignment_id,
                field,
            )
        )

    result: List[int] = []
    seen: Set[int] = set()

    for raw in value:
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise ValueError(
                "{} {} indexes must be integers".format(
                    alignment_id,
                    field,
                )
            )

        if raw < 1 or raw > count:
            raise ValueError(
                "{} {} index {} outside 1..{}".format(
                    alignment_id,
                    field,
                    raw,
                    count,
                )
            )

        if raw in seen:
            raise ValueError(
                "{} repeats {} index {}".format(
                    alignment_id,
                    field,
                    raw,
                )
            )

        seen.add(raw)
        result.append(raw)

    return result


def _validate_alignment_shape(
    alignment_id: str,
    status: str,
    source_indexes: Sequence[int],
    target_indexes: Sequence[int],
) -> None:
    source_count = len(source_indexes)
    target_count = len(target_indexes)

    if status not in ALIGNMENT_STATUSES:
        raise ValueError(
            "{} has unsupported status {}".format(
                alignment_id,
                status,
            )
        )

    if not source_count and not target_count:
        raise ValueError(
            "{} cannot have both source and target empty".format(
                alignment_id
            )
        )

    if status == "ALIGNED":
        valid = (
            source_count == 1
            and target_count == 1
        )

    elif status == "SPLIT":
        valid = (
            source_count == 1
            and target_count > 1
        )

    elif status == "MERGED":
        valid = (
            source_count > 1
            and target_count == 1
        )

    elif status == "UNALIGNED":
        valid = (
            (
                source_count == 1
                and target_count == 0
            )
            or
            (
                source_count == 0
                and target_count == 1
            )
        )

    else:
        valid = (
            source_count > 0
            and target_count > 0
        )

    if not valid:
        raise ValueError(
            "{} status {} is inconsistent with "
            "source={} target={}".format(
                alignment_id,
                status,
                source_count,
                target_count,
            )
        )


def _load_alignment_map(
    path: Path,
    source_count: int,
    target_count: int,
) -> List[Dict[str, Any]]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            "unable to read alignment map {}: {}".format(
                path,
                exc,
            )
        )

    if not isinstance(value, dict):
        raise ValueError(
            "alignment map must be a JSON object"
        )

    if value.get("format_version") != "1.0":
        raise ValueError(
            "alignment map format_version must be 1.0"
        )

    raw_alignments = value.get("alignments")

    if not isinstance(raw_alignments, list):
        raise ValueError(
            "alignment map requires alignments array"
        )

    if not raw_alignments and (
        source_count or target_count
    ):
        raise ValueError(
            "alignment map contains no alignments"
        )

    result: List[Dict[str, Any]] = []
    ids: Set[str] = set()
    consumed_source: Set[int] = set()
    consumed_target: Set[int] = set()

    for position, raw in enumerate(
        raw_alignments,
        1,
    ):
        if not isinstance(raw, dict):
            raise ValueError(
                "alignment {} must be an object".format(
                    position
                )
            )

        alignment_id = str(
            raw.get("id")
            or "A{:04d}".format(position)
        )

        if alignment_id in ids:
            raise ValueError(
                "duplicate alignment id {}".format(
                    alignment_id
                )
            )

        ids.add(alignment_id)

        status = str(
            raw.get("status") or ""
        ).upper()

        source_indexes = _normalize_indexes(
            raw.get("source", []),
            "source",
            alignment_id,
            source_count,
        )

        target_indexes = _normalize_indexes(
            raw.get("target", []),
            "target",
            alignment_id,
            target_count,
        )

        _validate_alignment_shape(
            alignment_id,
            status,
            source_indexes,
            target_indexes,
        )

        duplicate_source = (
            set(source_indexes)
            & consumed_source
        )

        if duplicate_source:
            raise ValueError(
                "{} reuses source paragraph(s) {}".format(
                    alignment_id,
                    sorted(duplicate_source),
                )
            )

        duplicate_target = (
            set(target_indexes)
            & consumed_target
        )

        if duplicate_target:
            raise ValueError(
                "{} reuses target paragraph(s) {}".format(
                    alignment_id,
                    sorted(duplicate_target),
                )
            )

        consumed_source.update(source_indexes)
        consumed_target.update(target_indexes)

        result.append(
            {
                "id": alignment_id,
                "status": status,
                "source": source_indexes,
                "target": target_indexes,
            }
        )

    expected_source = set(
        range(1, source_count + 1)
    )
    expected_target = set(
        range(1, target_count + 1)
    )

    if consumed_source != expected_source:
        missing = sorted(
            expected_source - consumed_source
        )
        raise ValueError(
            "source paragraph coverage mismatch; "
            "missing={}".format(missing)
        )

    if consumed_target != expected_target:
        missing = sorted(
            expected_target - consumed_target
        )
        raise ValueError(
            "target paragraph coverage mismatch; "
            "missing={}".format(missing)
        )

    return result


def _unit_from_alignment(
    index: int,
    alignment: Dict[str, Any],
    src: Sequence[Dict[str, Any]],
    tgt: Sequence[Dict[str, Any]],
    source_language: str,
    target_language: str,
) -> Dict[str, Any]:
    source_rows = [
        src[i - 1]
        for i in alignment["source"]
    ]

    target_rows = [
        tgt[i - 1]
        for i in alignment["target"]
    ]

    source_refs = [
        _paragraph_ref(row)
        for row in source_rows
    ]

    target_refs = [
        _paragraph_ref(row)
        for row in target_rows
    ]

    status = alignment["status"]

    if (
        status == "ALIGNED"
        and len(target_refs) == 1
    ):
        location = target_refs[0]
    else:
        location = "alignment:{}".format(
            alignment["id"]
        )

    unit: Dict[str, Any] = {
        "id": "U{:04d}".format(index),
        "alignment_id": alignment["id"],
        "alignment": status,
        "source": "\n\n".join(
            row["text"]
            for row in source_rows
        ),
        "target": "\n\n".join(
            row["text"]
            for row in target_rows
        ),
        "source_refs": source_refs,
        "target_refs": target_refs,
        "location": location,
    }

    if source_language:
        unit["source_language"] = source_language

    if target_language:
        unit["target_language"] = target_language

    return unit


def _explicit_units(
    alignment_path: Path,
    src: Sequence[Dict[str, Any]],
    tgt: Sequence[Dict[str, Any]],
    source_language: str,
    target_language: str,
) -> List[Dict[str, Any]]:
    alignments = _load_alignment_map(
        alignment_path,
        len(src),
        len(tgt),
    )

    return [
        _unit_from_alignment(
            index,
            alignment,
            src,
            tgt,
            source_language,
            target_language,
        )
        for index, alignment in enumerate(
            alignments,
            1,
        )
    ]


def _positional_units(
    src: Sequence[Dict[str, Any]],
    tgt: Sequence[Dict[str, Any]],
    source_language: str,
    target_language: str,
    allow_structural_mismatch: bool,
) -> List[Dict[str, Any]]:
    if len(src) != len(tgt):
        raise ValueError(
            "source/target non-empty paragraph counts differ: "
            "{} vs {}; refusing to drop unmatched content".format(
                len(src),
                len(tgt),
            )
        )

    units: List[Dict[str, Any]] = []

    for index, (source_row, target_row) in enumerate(
        zip(src, tgt),
        1,
    ):
        structurally_aligned = (
            source_row["part"],
            source_row["paragraph_ordinal"],
        ) == (
            target_row["part"],
            target_row["paragraph_ordinal"],
        )

        if (
            not structurally_aligned
            and not allow_structural_mismatch
        ):
            raise ValueError(
                "paragraph structure diverges at aligned item {}".format(
                    index
                )
            )

        alignment_id = "A{:04d}".format(index)
        source_ref = _paragraph_ref(source_row)
        target_ref = _paragraph_ref(target_row)

        unit: Dict[str, Any] = {
            "id": "U{:04d}".format(index),
            "alignment_id": alignment_id,
            "source": source_row["text"],
            "target": target_row["text"],
            "source_refs": [source_ref],
            "target_refs": [target_ref],
            "location": target_ref,
            "alignment": (
                "ALIGNED"
                if structurally_aligned
                else "AMBIGUOUS"
            ),
        }

        if source_language:
            unit["source_language"] = (
                source_language
            )

        if target_language:
            unit["target_language"] = (
                target_language
            )

        units.append(unit)

    return units


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument("source_docx")
    parser.add_argument("target_docx")

    parser.add_argument(
        "--output",
        required=True,
    )

    parser.add_argument(
        "--source-language",
        default="",
    )

    parser.add_argument(
        "--target-language",
        default="",
    )

    parser.add_argument(
        "--alignment-map",
        help=(
            "explicit JSON alignment map using 1-based "
            "non-empty paragraph indexes"
        ),
    )

    parser.add_argument(
        "--allow-structural-mismatch",
        action="store_true",
        help=(
            "without --alignment-map, allow positional pairing "
            "when paragraph counts match but part/ordinal "
            "structure differs"
        ),
    )

    args = parser.parse_args()

    if (
        args.alignment_map
        and args.allow_structural_mismatch
    ):
        parser.error(
            "--alignment-map and "
            "--allow-structural-mismatch are mutually exclusive"
        )

    try:
        src = extract_paragraphs(
            Path(args.source_docx)
        )
        tgt = extract_paragraphs(
            Path(args.target_docx)
        )

        if args.alignment_map:
            units = _explicit_units(
                Path(args.alignment_map),
                src,
                tgt,
                args.source_language,
                args.target_language,
            )
        else:
            units = _positional_units(
                src,
                tgt,
                args.source_language,
                args.target_language,
                args.allow_structural_mismatch,
            )

        write_jsonl(
            Path(args.output),
            units,
        )

        print(
            "Extracted {} bilingual units".format(
                len(units)
            )
        )

        return 0

    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())

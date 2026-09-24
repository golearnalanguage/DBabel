#!/usr/bin/env python3
"""Extract paragraph-aligned bilingual units from source and target DOCX files.

The extractor is intentionally strict. Source and target must contain the same
number of non-empty paragraphs. --allow-structural-mismatch permits positional
pairing only when counts are equal; it never drops unmatched content.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from docx_review_adapter import extract_paragraphs
from review_model import write_jsonl


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source_docx")
    p.add_argument("target_docx")
    p.add_argument("--output", required=True)
    p.add_argument("--source-language")
    p.add_argument("--target-language")
    p.add_argument(
        "--allow-structural-mismatch",
        action="store_true",
        help=(
            "allow positional pairing when paragraph counts match but "
            "part/ordinal structure differs; unequal counts always fail closed"
        ),
    )
    a = p.parse_args()

    src = extract_paragraphs(Path(a.source_docx))
    tgt = extract_paragraphs(Path(a.target_docx))

    if len(src) != len(tgt):
        p.error(
            "source/target non-empty paragraph counts differ: {} vs {}; "
            "refusing to drop unmatched content".format(len(src), len(tgt))
        )

    units = []

    for i, (s, t) in enumerate(zip(src, tgt), 1):
        aligned = (
            s["part"],
            s["paragraph_ordinal"],
        ) == (
            t["part"],
            t["paragraph_ordinal"],
        )

        if not aligned and not a.allow_structural_mismatch:
            p.error(
                "paragraph structure diverges at aligned item {}".format(i)
            )

        unit = {
            "id": "U{:04d}".format(i),
            "source": s["text"],
            "target": t["text"],
            "location": "docx:{}:p={}".format(
                t["part"],
                t["paragraph_ordinal"],
            ),
            "alignment": "ALIGNED" if aligned else "AMBIGUOUS",
        }

        if a.source_language:
            unit["source_language"] = a.source_language

        if a.target_language:
            unit["target_language"] = a.target_language

        units.append(unit)

    write_jsonl(Path(a.output), units)

    print("Extracted {} bilingual units".format(len(units)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

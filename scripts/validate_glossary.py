#!/usr/bin/env python3
"""Validate a DBabel project glossary JSON or CSV file."""
import argparse
import json
from pathlib import Path

from glossary_io import GlossaryError, load_glossary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("glossary", help="Project glossary (.json or .csv)")
    parser.add_argument(
        "--normalized-json",
        help="Optional path to write the normalized canonical JSON form",
    )
    args = parser.parse_args()

    try:
        glossary = load_glossary(args.glossary)
    except GlossaryError as exc:
        parser.exit(1, "{}\n".format(exc))

    if args.normalized_json:
        out = Path(args.normalized_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(glossary, handle, ensure_ascii=False, indent=2)
            handle.write("\n")

    print("Project glossary valid: {} entries.".format(len(glossary.get("entries", []))))


if __name__ == "__main__":
    main()

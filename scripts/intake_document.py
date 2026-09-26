#!/usr/bin/env python3
"""Extract a document into a review session with an explicit language per target."""
import argparse
import json
from pathlib import Path
from review_exchange import read_document, create_intake


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source'); p.add_argument('--target')
    p.add_argument('--source-language'); p.add_argument('--target-languages', help='Comma-separated language tags')
    p.add_argument('--output'); p.add_argument('--inspect', action='store_true')
    p.add_argument('--confirm-positional-alignment', action='store_true')
    a = p.parse_args()
    try:
        if a.inspect:
            result = read_document(Path(a.source))
            print(json.dumps(result, ensure_ascii=False, indent=2)); return
        if not a.output or not a.source_language or not a.target_languages:
            p.error('--output, --source-language and --target-languages are required to create a session')
        print(create_intake(Path(a.source), Path(a.output), a.source_language, a.target_languages.split(','),
                            Path(a.target) if a.target else None, a.confirm_positional_alignment))
    except (ValueError, OSError) as exc: p.exit(2, str(exc)+'\n')


if __name__ == '__main__': main()

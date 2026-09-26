#!/usr/bin/env python3
"""Export a review snapshot, including pending rows, in a portable document format."""
import argparse
from pathlib import Path
from review_model import load_bundle
from review_exchange import RESULT_FORMATS, render_result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('bundle'); p.add_argument('--format', choices=sorted(RESULT_FORMATS), default='json')
    p.add_argument('--output', required=True); a = p.parse_args()
    try:
        content = render_result(load_bundle(Path(a.bundle)), a.format)
        with Path(a.output).open('x', encoding='utf-8', newline='') as f: f.write(content)
    except (OSError, ValueError) as exc: p.exit(2, str(exc)+'\n')
    print(a.output)


if __name__ == '__main__': main()

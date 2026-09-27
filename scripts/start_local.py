#!/usr/bin/env python3
"""Start an offline Workbench from any directory, copying demo data on first use."""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, help='Existing review session (absolute path recommended)')
    parser.add_argument('--original', type=Path, help='Original native document used for export')
    parser.add_argument('--output', type=Path, help='Native reviewed output path')
    parser.add_argument('--port', type=int, default=0, help='Local port; 0 chooses an available port')
    parser.add_argument('--no-browser', action='store_true', help='Print the URL without opening a browser')
    args = parser.parse_args()

    if not 0 <= args.port <= 65535:
        parser.error('Port must be between 0 and 65535')

    if bool(args.original) != bool(args.output):
        parser.error('--original and --output must be supplied together')

    bundle = args.bundle.expanduser().resolve() if args.bundle else ROOT/'output'/'local-demo.dbreview'

    if args.bundle and not bundle.is_dir():
        parser.error('Session not found: ' + str(bundle))

    original = (
        args.original.expanduser().resolve()
        if args.original
        else None
    )

    output = (
        args.output.expanduser().resolve()
        if args.output
        else None
    )

    if original is not None:
        if not original.is_file():
            parser.error(
                'Original file not found: '
                + str(original)
            )

        if output == original:
            parser.error(
                'Output must not overwrite the original'
            )

        if (
            output.suffix.lower()
            != original.suffix.lower()
        ):
            parser.error(
                'Output extension must match the original'
            )
    try:
        import yaml
        import jsonschema
    except ImportError:
        parser.exit(1, 'Install dependencies with this Python first:\n"{}" -m pip install -r "{}"\n'.format(sys.executable, ROOT/'requirements-dev.txt'))
    if not bundle.exists():
        bundle.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(ROOT/'examples'/'review_workbench_demo.dbreview', bundle)
    print('Session: ' + str(bundle), flush=True)
    print('Keep this terminal open. Open the complete printed URL including #token= in your browser.', flush=True)
    command = [
        sys.executable,
        '-u',
        str(
            ROOT
            / 'scripts'
            / 'start_review_workbench.py'
        ),
        str(bundle),
        '--port',
        str(args.port),
    ]

    if original is not None:
        command.extend([
            '--original',
            str(original),
            '--output',
            str(output),
        ])

    if args.no_browser:
        command.append('--no-browser')
    try:
        return subprocess.call(command, cwd=ROOT)
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    raise SystemExit(main())

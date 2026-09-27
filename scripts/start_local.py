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
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true', help='Print the URL without opening a browser')
    args = parser.parse_args()
    bundle = args.bundle.expanduser().resolve() if args.bundle else ROOT/'output'/'local-demo.dbreview'
    if args.bundle and not bundle.is_dir():
        parser.error('Session not found: ' + str(bundle))
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
    command = [sys.executable, '-u', str(ROOT/'scripts'/'start_review_workbench.py'), str(bundle), '--port', str(args.port)]
    if args.no_browser:
        command.append('--no-browser')
    try:
        return subprocess.call(command, cwd=ROOT)
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    raise SystemExit(main())

"""Run unit tests with private disposable memory, settings and rejections."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def main():
    with tempfile.TemporaryDirectory(prefix='dbabel-unit-tests-') as directory:
        root = Path(directory)
        (root / 'rejections.json').write_text('[]', encoding='utf-8')
        environment = dict(os.environ,
            DBABEL_TRANSLATION_MEMORY=str(root / 'memory.sqlite3'),
            DBABEL_GENERAL_TERMS_SETTINGS=str(root / 'settings.json'),
            DBABEL_REJECTION_MEMORY=str(root / 'rejections.json'))
        args = sys.argv[1:] or ['discover', '-s', 'tests', '-v']
        return subprocess.run([sys.executable, '-m', 'unittest', *args], cwd=ROOT, env=environment).returncode

if __name__ == '__main__':
    raise SystemExit(main())

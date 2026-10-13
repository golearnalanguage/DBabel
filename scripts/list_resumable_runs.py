"""Discover recoverable translations without changing run state."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.run_lease import resumable_runs

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(resumable_runs(args.workspace_root), ensure_ascii=False))

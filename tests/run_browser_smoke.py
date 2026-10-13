#!/usr/bin/env python3
"""Run browser checks against disposable synthetic review sessions only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples/review_workbench_demo.dbreview"
CHECKS = {
    "decisions": "workbench_browser_smoke.cjs",
    "exchange": "workbench_exchange_smoke.cjs",
    "native": "workbench_native_smoke.cjs",
    "accessibility": "workbench_accessibility_smoke.cjs",
    "recovery": "portable_recovery_smoke.cjs",
}


def fixture_hashes():
    return {str(p.relative_to(DEMO)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in DEMO.rglob("*") if p.is_file()}


def user_state_hashes():
    """Observe default user storage without opening or creating a database."""
    directory = (Path.home() / "Library/Application Support/DBabel"
                 if sys.platform == "darwin" else Path.home() / ".dbabel")
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in directory.glob("*") if p.is_file()
            and p.name.startswith(("translation-memory", "general-terms-settings"))}


def long_bundle(bundle):
    """Extend the existing synthetic demo for cross-page recovery checks."""
    units = [json.loads(line) for line in (bundle / "units.jsonl").read_text().splitlines() if line]
    for index in range(len(units), 76):
        units.append(dict(units[2], id="LONG_{:04d}".format(index),
                          location="Synthetic paragraph {}".format(index),
                          source="合成恢复检查 {}".format(index),
                          current_target="Synthetic recovery check {}".format(index),
                          labels=[], evidence_refs=[]))
    (bundle / "units.jsonl").write_text("\n".join(json.dumps(u, ensure_ascii=False) for u in units) + "\n", encoding="utf-8")
    sys.path.insert(0, str(ROOT / "scripts"))
    from review_model import default_decision
    decisions = [default_decision(u["id"]) for u in units]
    (bundle / "decisions.json").write_text(json.dumps(decisions, ensure_ascii=False), encoding="utf-8")
    session_path = bundle / "session.json"
    session = json.loads(session_path.read_text())
    session["session_id"] = "RS_SYNTHETIC_BROWSER_RECOVERY"
    session["counts"]["units"] = len(units)
    session_path.write_text(json.dumps(session, ensure_ascii=False), encoding="utf-8")


def start_server(bundle, log_path, environment):
    process = subprocess.Popen(
        [sys.executable, "-u", str(ROOT / "scripts/start_review_workbench.py"),
         str(bundle), "--port", "0", "--no-browser"],
        cwd=ROOT, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    lines = queue.Queue()

    def read_output():
        with log_path.open("w", encoding="utf-8") as log:
            for line in process.stdout:
                log.write(re.sub(r"#token=\S+", "#token=<redacted>", line))
                log.flush()
                lines.put(line)
        lines.put(None)

    threading.Thread(target=read_output, daemon=True).start()
    deadline = time.monotonic() + 20
    try:
        while time.monotonic() < deadline:
            line = lines.get(timeout=max(0.01, deadline - time.monotonic()))
            if line is None:
                raise RuntimeError("Workbench exited before startup; inspect " + str(log_path))
            if line.startswith("Open: "):
                return process, line[6:].strip()
        raise RuntimeError("Workbench startup timed out")
    except Exception:
        stop_server(process)
        raise


def stop_server(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(ROOT / "output/browser-smoke"))
    parser.add_argument("--only", nargs="+", choices=CHECKS, default=list(CHECKS))
    args = parser.parse_args()
    output = Path(args.output).resolve()
    if output == DEMO or DEMO in output.parents:
        parser.error("Browser artifacts must be outside the tracked demo fixture")
    output.mkdir(parents=True, exist_ok=True)
    node = shutil.which("node")
    if not node:
        parser.error("Node.js is required; run npm ci before these optional checks")
    subprocess.run([node, "-e", "require('playwright');require('axe-core')"], cwd=ROOT, check=True, timeout=15)
    before = fixture_hashes()
    user_before = user_state_hashes()
    results = []
    try:
        for name in args.only:
            artifacts = output / name
            artifacts.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="dbabel-browser-") as directory:
                scratch = Path(directory)
                bundle = scratch / "synthetic.dbreview"
                shutil.copytree(DEMO, bundle)
                if name == "recovery":
                    long_bundle(bundle)
                portable = scratch / "review.html"
                subprocess.run([sys.executable, str(ROOT / "scripts/build_portable_review.py"),
                                str(bundle), "--output", str(portable)],
                               cwd=ROOT, check=True, capture_output=True, timeout=30)
                # Review actions also write local memory and settings. Keep all
                # three overrides inside the synthetic fixture's lifetime.
                environment = dict(os.environ,
                                   DBABEL_TRANSLATION_MEMORY=str(scratch / "translation-memory.sqlite3"),
                                   DBABEL_GENERAL_TERMS_SETTINGS=str(scratch / "general-terms.json"),
                                   DBABEL_REJECTION_MEMORY=str(scratch / "rejected-translations.json"))
                server, url = start_server(bundle, artifacts / "server.log", environment)
                (artifacts / "fixture.json").write_text(json.dumps({
                    "synthetic_bundle": str(bundle), "isolated_storage": {
                        key: environment[key] for key in (
                            "DBABEL_TRANSLATION_MEMORY", "DBABEL_GENERAL_TERMS_SETTINGS", "DBABEL_REJECTION_MEMORY")
                    }}, indent=2) + "\n")
                try:
                    env = dict(environment, DBABEL_TEST_URL=url,
                               DBABEL_TEST_PORTABLE=str(portable),
                               DBABEL_TEST_OUTPUT=str(artifacts),
                               DBABEL_SCREENSHOT=str(artifacts / "portable.png"))
                    try:
                        run = subprocess.run([node, str(ROOT / "tests" / CHECKS[name])],
                                             cwd=ROOT, env=env, capture_output=True,
                                             text=True, timeout=240)
                    except subprocess.TimeoutExpired as exc:
                        partial = "".join(value.decode("utf-8", errors="replace")
                                          if isinstance(value, bytes) else (value or "")
                                          for value in (exc.stdout, exc.stderr))
                        (artifacts / "browser.log").write_text(
                            re.sub(r"#token=[^\s'\"]+", "#token=<redacted>", partial) + "\nBrowser check timed out.\n", encoding="utf-8")
                        results.append({"check": name, "passed": False, "timed_out": True})
                        raise RuntimeError("{} timed out; inspect {}".format(name, artifacts / "browser.log")) from exc
                    log = re.sub(r"#token=[^\s'\"]+", "#token=<redacted>", run.stdout + run.stderr)
                    (artifacts / "browser.log").write_text(log, encoding="utf-8")
                    results.append({"check": name, "passed": run.returncode == 0})
                    print("{}: {}".format(name, "PASS" if run.returncode == 0 else "FAIL"), flush=True)
                    if run.returncode:
                        raise RuntimeError("{} failed; inspect {}".format(name, artifacts / "browser.log"))
                finally:
                    stop_server(server)
                    for session_path in scratch.rglob("session.json"):
                        snapshot = artifacts / "sessions" / session_path.parent.relative_to(scratch)
                        snapshot.mkdir(parents=True, exist_ok=True)
                        for filename in ("session.json", "decisions.json", "events.jsonl", "ui_state.json"):
                            source = session_path.parent / filename
                            if source.is_file():
                                shutil.copyfile(source, snapshot / filename)
    finally:
        unchanged = fixture_hashes() == before
        user_unchanged = user_state_hashes() == user_before
        (output / "summary.json").write_text(json.dumps({"checks": results, "demo_unchanged": unchanged,
                                                        "user_state_unchanged": user_unchanged}, indent=2) + "\n")
        if not unchanged:
            raise RuntimeError("Tracked synthetic demo was changed during browser checks")
        if not user_unchanged:
            raise RuntimeError("Default user storage changed while browser checks ran; inspect concurrent activity")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

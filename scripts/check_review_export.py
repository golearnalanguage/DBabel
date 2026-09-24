#!/usr/bin/env python3
"""Run a fresh deterministic recheck and evaluate the DBabel review export gate."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
if str(HERE) not in sys.path:sys.path.insert(0,str(HERE))
from review_model import evaluate_export_gate,fresh_recheck_all,load_bundle,save_decisions,write_json

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("bundle");p.add_argument("--repo-root",default=str(ROOT));p.add_argument("--original");p.add_argument("--glossary");p.add_argument("--receipt");a=p.parse_args()
    data=load_bundle(Path(a.bundle));updated,qa=fresh_recheck_all(data,Path(a.repo_root),Path(a.glossary) if a.glossary else None);save_decisions(data["bundle"],updated);data=load_bundle(Path(a.bundle));receipt=evaluate_export_gate(data,qa,Path(a.original) if a.original else None)
    if a.receipt:write_json(Path(a.receipt),receipt)
    print(json.dumps(receipt,ensure_ascii=False,indent=2));return 0 if receipt["status"]=="AUTHORIZED" else 1
if __name__=="__main__":raise SystemExit(main())

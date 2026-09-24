#!/usr/bin/env python3
"""Import decisions exported by DBabel Portable Review into a .dbreview bundle."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
if str(HERE) not in sys.path: sys.path.insert(0,str(HERE))
from review_model import append_event,load_bundle,normalize_decision,save_decisions,utc_now

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("bundle");p.add_argument("decisions");a=p.parse_args()
    bundle=Path(a.bundle);data=load_bundle(bundle);payload=json.loads(Path(a.decisions).read_text(encoding="utf-8"))
    if payload.get("session_id")!=data["session"]["session_id"]: p.error("decision file belongs to a different review session")
    rows=payload.get("decisions")
    if not isinstance(rows,list): p.error("portable decision file requires decisions array")
    incoming={x.get("unit_id"):x for x in rows if isinstance(x,dict)}
    if set(incoming)!=set(data["units_by_id"]): p.error("portable decision coverage does not match review session")
    saved=[]
    for unit in data["units"]:
        uid=unit["id"];prev=data["decisions_by_id"][uid];row=incoming[uid]
        # Preserve portable decision revision as evidence only; normalize increments the local revision and invalidates QA.
        nextd=normalize_decision(unit,row,prev);saved.append(nextd)
        if nextd["status"]!=prev["status"] or nextd.get("approved_target")!=prev.get("approved_target"):
            append_event(bundle/"events.jsonl",{"event":"DECISION_CHANGED","unit_id":uid,"at":utc_now(),"revision":nextd["revision"],"actor":"HUMAN","from_status":prev["status"],"to_status":nextd["status"],"detail":"Imported from portable review"})
    save_decisions(bundle,saved);print("Imported {} decisions".format(len(saved)));return 0
if __name__=="__main__": raise SystemExit(main())

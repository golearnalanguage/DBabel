#!/usr/bin/env python3
"""Build a self-contained offline HTML reviewer from a .dbreview bundle."""
from __future__ import annotations
import argparse, base64, json, sys
from pathlib import Path
HERE=Path(__file__).resolve().parent; ROOT=HERE.parent
if str(HERE) not in sys.path: sys.path.insert(0,str(HERE))
from review_model import load_bundle

PLACEHOLDERS=("__DBABEL_DATA__","__DBABEL_LOGO__","__DBABEL_CSS__","__DBABEL_PORTABLE_JS__")

def build(bundle: Path, output: Path) -> Path:
    data=load_bundle(bundle)
    payload={k:data[k] for k in ("session","units","issues","evidence","decisions")}
    encoded=base64.b64encode(json.dumps(payload,ensure_ascii=False,separators=(",",":")).encode("utf-8")).decode("ascii")
    template=(ROOT/"review_workbench"/"portable_template.html").read_text(encoding="utf-8")
    for marker in PLACEHOLDERS:
        if template.count(marker)!=1: raise ValueError("portable placeholder contract violated: "+marker)
    logo=base64.b64encode((ROOT/"review_workbench"/"static"/"dbabel-workbench-logo.png").read_bytes()).decode("ascii")
    css=(ROOT/"review_workbench"/"static"/"style.css").read_text(encoding="utf-8")
    js=(ROOT/"review_workbench"/"portable_app.js").read_text(encoding="utf-8")
    js=(ROOT/"review_workbench"/"static"/"workbench_views.js").read_text(encoding="utf-8")+"\n"+js
    rendered=(template.replace("__DBABEL_DATA__",encoded)
                      .replace("__DBABEL_LOGO__",logo)
                      .replace("__DBABEL_CSS__",css)
                      .replace("__DBABEL_PORTABLE_JS__",js))
    with output.open("w",encoding="utf-8",newline="\n") as fh: fh.write(rendered)
    return output

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("bundle");p.add_argument("--output",required=True);a=p.parse_args()
    out=build(Path(a.bundle),Path(a.output));print(out);return 0
if __name__=="__main__": raise SystemExit(main())

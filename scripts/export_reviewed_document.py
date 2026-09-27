#!/usr/bin/env python3
"""Export an approved DOCX, TXT or Markdown copy with bilingual and Agent handoffs."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from docx_review_adapter import (
    DocxExportError,
    _anchor_identity,
    apply_reviewed_docx,
    round_trip_verify,
    verify_non_target_text_unchanged,
    verify_package_fidelity,
)
from build_post_review_report import build_report, render_markdown
from review_exchange import render_result
from text_review_adapter import apply_reviewed_text
from review_model import (
    evaluate_export_gate,
    fresh_recheck_all,
    load_bundle,
    save_decisions,
    sha256_file,
    utc_now,
    write_json,
)


def export_bundle(
    bundle: Path,
    repo_root: Path,
    original: Path,
    output: Path,
    glossary: Optional[Path] = None,
    receipt_path: Optional[Path] = None,
    qa_runner=None,
    export_mode: str = "FINAL",
) -> Dict[str, Any]:
    receipt_path = receipt_path or Path(str(output) + '.receipt.json')
    sidecars = {kind: Path(str(output) + suffix) for kind, suffix in {
        'handoff_json': '.handoff.json', 'handoff_markdown': '.handoff.md',
        'bilingual_html': '.bilingual.html', 'receipt': '.receipt.json'}.items()}
    sidecars['receipt'] = receipt_path
    destinations = [output] + list(sidecars.values())
    if len({p.resolve() for p in destinations}) != len(destinations):
        raise ValueError('Export document and sidecar paths must be distinct')
    for path in destinations:
        if path.resolve() == original.resolve() or path.exists():
            raise ValueError('Export destination already exists or is the original: ' + str(path))
    data = load_bundle(bundle)
    updated_decisions, qa_by_unit = fresh_recheck_all(
        data, repo_root, glossary_path=glossary, qa_runner=qa_runner
    )
    save_decisions(data["bundle"], updated_decisions)
    data = load_bundle(bundle)
    gate = evaluate_export_gate(data, fresh_qa_by_unit=qa_by_unit, original_path=original, export_mode=export_mode)

    if gate["status"] != "AUTHORIZED":
        if receipt_path:
            write_json(receipt_path, gate)
        return gate

    if output.resolve() == original.resolve():
        gate["status"] = "FAILED"
        gate["blockers"].append("refusing to overwrite original document")
        if receipt_path:
            write_json(receipt_path, gate)
        return gate
    if output.exists():
        gate["status"] = "FAILED"
        gate["blockers"].append("output already exists: {}".format(output))
        if receipt_path:
            write_json(receipt_path, gate)
        return gate

    suffix = original.suffix.lower()
    if suffix not in {'.docx', '.txt', '.md'} or output.suffix.lower() != suffix:
        gate["status"] = "FAILED"
        gate["blockers"].append("native export requires matching .docx, .txt or .md input/output extensions")
        if receipt_path:
            write_json(receipt_path, gate)
        return gate

    created = []
    try:
        decisions_by_id = data["decisions_by_id"]
        export_units = data["units"]
        if export_mode == "CHECKPOINT":
            included = set(gate["review_scope"]["included_unit_ids"])
            export_units = [unit for unit in export_units if unit["id"] in included]
            omitted_anchors = {
                _anchor_identity(anchor) for uid, anchor in data["anchors"].items()
                if uid not in included and anchor.get("status") == "RESOLVED"
            }
            for unit in export_units:
                anchor = data["anchors"].get(unit["id"])
                changed_target = decisions_by_id[unit["id"]].get("approved_target") != unit["current_target"]
                if changed_target and anchor and anchor.get("status") == "RESOLVED" and _anchor_identity(anchor) in omitted_anchors:
                    raise DocxExportError("checkpoint change overlaps an unreviewed paragraph")
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=output.parent) as staging:
            staged = Path(staging)/output.name
            if suffix == '.docx':
                changed = apply_reviewed_docx(original, staged, export_units, decisions_by_id, data['anchors'])
                checks = round_trip_verify(staged, export_units, decisions_by_id, data['anchors'])
                checks.extend(verify_non_target_text_unchanged(original, staged, data['anchors'], decisions_by_id, export_units))
                checks.extend(verify_package_fidelity(original, staged))
            else:
                changed = apply_reviewed_text(original, staged, export_units, decisions_by_id, data['anchors'])
                checks = ['UTF-8 BOM, original line endings, blank lines and all unmodified lines preserved',
                          'Approved text changes round-trip verified; Markdown markup in edited lines needs review']
            with output.open('xb') as stream:
                created.append(output)
                stream.write(staged.read_bytes())
        gate["status"] = "VERIFIED"
        gate["checked_at"] = utc_now()
        gate["output"] = {
            "path": str(output),
            "sha256": sha256_file(output),
            "format": suffix.lstrip('.'),
        }
        gate["round_trip"] = {
            "status": "PASS",
            "checks": checks + ["{} reviewed unit(s) changed".format(len(changed))],
        }
        handoff = build_report(data, gate)
        contents = {
            'handoff_json': json.dumps(handoff, ensure_ascii=False, indent=2)+'\n',
            'handoff_markdown': render_markdown(handoff),
            'bilingual_html': render_result(data, 'html', {u['unit_id']: u['exported_target'] for u in handoff['units']}),
        }
        gate['artifacts'] = []
        for kind, content in contents.items():
            path = sidecars[kind]
            with path.open('x', encoding='utf-8', newline='\n') as stream:
                created.append(path)
                stream.write(content)
            gate['artifacts'].append({'kind': kind, 'path': str(path), 'sha256': sha256_file(path)})
    except (OSError, DocxExportError, ValueError) as exc:
        for path in created:
            path.unlink()
        gate.pop('artifacts', None)
        gate.pop('output', None)
        gate["status"] = "FAILED"
        gate["blockers"].append(str(exc))
        gate["round_trip"] = {"status": "FAIL", "checks": [str(exc)]}

    if receipt_path:
        write_json(receipt_path, gate)
    return gate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", help=".dbreview directory")
    parser.add_argument("--repo-root", default=str(HERE.parent), help="DBabel repository root")
    parser.add_argument("--original", required=True, help="Original DOCX, TXT or MD whose SHA-256 must match the session")
    parser.add_argument("--output", required=True, help="New document path with the same extension; original is never overwritten")
    parser.add_argument("--glossary")
    parser.add_argument("--receipt")
    parser.add_argument("--export-mode", choices=["FINAL", "CHECKPOINT"], default="FINAL")
    args = parser.parse_args()

    receipt = export_bundle(
        Path(args.bundle),
        Path(args.repo_root).resolve(),
        Path(args.original).resolve(),
        Path(args.output).resolve(),
        Path(args.glossary).resolve() if args.glossary else None,
        Path(args.receipt).resolve() if args.receipt else None,
        export_mode=args.export_mode,
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    if receipt["status"] == "VERIFIED":
        return 0
    if receipt["status"] == "AUTHORIZED":
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Loss-minimizing XLSX review adapter for DBabel.

Only explicitly approved anchored worksheet cell elements are modified. All
untouched OOXML package part payloads are preserved byte-for-byte. Formula cells
fail closed and are never rewritten.
"""
from __future__ import annotations

import html
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List
from xml.etree import ElementTree as ET

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS = {"m": MAIN_NS}
CELL_RE = re.compile(r"^[A-Z]{1,3}[1-9][0-9]*$")
COMPLETED = {
    "ACCEPT_SUGGESTION",
    "KEEP_CURRENT",
    "USER_EDITED",
    "WAIVED",
    "DRAFT_SUGGESTION",  # Transient native-copy target; never a human decision.
}


class XlsxExportError(ValueError):
    pass


def _split_location(location: str):
    if ":" not in location:
        raise XlsxExportError(
            "XLSX location must be worksheet-part:CELL: " + location
        )
    part, cell = location.rsplit(":", 1)
    if not part.startswith("xl/worksheets/") or not CELL_RE.fullmatch(cell):
        raise XlsxExportError("unsupported XLSX location: " + location)
    return part, cell


def _shared_strings(zf: zipfile.ZipFile) -> List[str]:
    name = "xl/sharedStrings.xml"
    if name not in zf.namelist():
        return []
    root = ET.fromstring(zf.read(name))
    values = []
    for si in root.findall("m:si", NS):
        values.append(
            "".join((node.text or "") for node in si.findall(".//m:t", NS))
        )
    return values


def _cell_map(xml_bytes: bytes):
    root = ET.fromstring(xml_bytes)
    return {
        cell.get("r"): cell
        for cell in root.findall(".//m:c", NS)
        if cell.get("r")
    }


def _cell_text(cell, shared: List[str]) -> str:
    if cell.find("m:f", NS) is not None:
        raise XlsxExportError("formula cell cannot be rewritten")

    kind = cell.get("t")
    if kind == "inlineStr":
        return "".join(
            (node.text or "")
            for node in cell.findall(".//m:is//m:t", NS)
        )

    value = cell.find("m:v", NS)
    raw = "" if value is None or value.text is None else value.text

    if kind == "s":
        try:
            return shared[int(raw)]
        except (ValueError, IndexError):
            raise XlsxExportError("invalid shared-string index")

    if kind == "b":
        return "TRUE" if raw == "1" else "FALSE"

    return raw


def build_anchors(
    original: Path,
    units: Iterable[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    anchors: Dict[str, Dict[str, Any]] = {}
    grouped: Dict[str, List[Any]] = {}

    for unit in units:
        try:
            part, cell = _split_location(str(unit.get("location") or ""))
        except XlsxExportError as exc:
            anchors[unit["id"]] = {
                "id": "A_" + unit["id"],
                "unit_id": unit["id"],
                "status": "BLOCKED",
                "reason": str(exc),
                "original_text": str(unit.get("current_target") or ""),
            }
            continue

        grouped.setdefault(part, []).append((unit, cell))

    with zipfile.ZipFile(original, "r") as zf:
        shared = _shared_strings(zf)
        names = set(zf.namelist())

        for part, items in grouped.items():
            if part not in names:
                for unit, cell in items:
                    anchors[unit["id"]] = {
                        "id": "A_" + unit["id"],
                        "unit_id": unit["id"],
                        "status": "BLOCKED",
                        "reason": "worksheet part not found: " + part,
                        "part": part,
                        "cell": cell,
                        "original_text": str(
                            unit.get("current_target") or ""
                        ),
                    }
                continue

            cells = _cell_map(zf.read(part))
            for unit, cell_ref in items:
                cell = cells.get(cell_ref)
                if cell is None:
                    reason = "cell not found"
                    actual = None
                else:
                    try:
                        actual = _cell_text(cell, shared)
                        reason = ""
                    except XlsxExportError as exc:
                        actual = None
                        reason = str(exc)

                expected = str(unit.get("current_target") or "")
                if actual is not None and actual != expected:
                    reason = "anchor text mismatch"

                anchors[unit["id"]] = {
                    "id": "A_" + unit["id"],
                    "unit_id": unit["id"],
                    "status": "RESOLVED" if not reason else "BLOCKED",
                    "reason": reason,
                    "part": part,
                    "cell": cell_ref,
                    "original_text": expected,
                }

    return anchors


def _cell_pattern(cell_ref: str):
    quoted = re.escape(cell_ref)
    return re.compile(
        r'<c\b(?=[^>]*\br=(["\'])'
        + quoted
        + r'\1)[^>]*(?:/>|>.*?</c>)',
        re.S,
    )


def _patch_cell(xml_text: str, cell_ref: str, replacement: str) -> str:
    pattern = _cell_pattern(cell_ref)
    matches = list(pattern.finditer(xml_text))

    if len(matches) != 1:
        raise XlsxExportError(
            "{} expected one cell element, found {}".format(
                cell_ref, len(matches)
            )
        )

    block = matches[0].group(0)
    if re.search(r"<f(?:\s|>)", block):
        raise XlsxExportError("{} is a formula cell".format(cell_ref))

    start_match = re.match(r"<c\b[^>]*(?:/?>)", block, re.S)
    if not start_match:
        raise XlsxExportError(
            "{} has malformed cell XML".format(cell_ref)
        )

    start = start_match.group(0)
    if start.endswith("/>"):
        inner = ""
        core = start[:-2]
    else:
        inner = block[len(start):-4]
        core = start[:-1]

    core = re.sub(r'\s+t=(["\']).*?\1', "", core)

    cleaned = re.sub(
        r"<v(?:\s[^>]*)?/>|<v(?:\s[^>]*)?>.*?</v>",
        "",
        inner,
        flags=re.S,
    )
    cleaned = re.sub(
        r"<is(?:\s[^>]*)?/>|<is(?:\s[^>]*)?>.*?</is>",
        "",
        cleaned,
        flags=re.S,
    )

    escaped = html.escape(replacement, quote=False)
    preserve = (
        ' xml:space="preserve"'
        if replacement[:1].isspace() or replacement[-1:].isspace()
        else ""
    )
    inline = "<is><t{}>{}</t></is>".format(preserve, escaped)

    ext = re.search(r"<extLst(?:\s|>)", cleaned)
    if ext:
        new_inner = (
            cleaned[:ext.start()] + inline + cleaned[ext.start():]
        )
    else:
        new_inner = cleaned + inline

    new_block = core + ' t="inlineStr">' + new_inner + "</c>"
    return (
        xml_text[:matches[0].start()]
        + new_block
        + xml_text[matches[0].end():]
    )


def _approved_changes(units, decisions_by_id, anchors):
    changes: Dict[str, Dict[str, str]] = {}
    changed_ids = []

    for unit in units:
        decision = decisions_by_id[unit["id"]]
        if decision.get("status") not in COMPLETED:
            continue

        approved = str(
            decision.get(
                "approved_target",
                unit.get("current_target", ""),
            )
        )
        current = str(unit.get("current_target") or "")
        if approved == current:
            continue

        anchor = anchors.get(unit["id"]) or {}
        if anchor.get("status") != "RESOLVED":
            raise XlsxExportError(
                "{} has no resolved XLSX anchor: {}".format(
                    unit["id"],
                    anchor.get("reason") or "unknown reason",
                )
            )

        part = anchor.get("part")
        cell = anchor.get("cell")
        if not part or not cell:
            raise XlsxExportError(
                "{} anchor is incomplete".format(unit["id"])
            )

        part_changes = changes.setdefault(part, {})
        if cell in part_changes:
            raise XlsxExportError(
                "multiple review units target {}:{}".format(part, cell)
            )

        part_changes[cell] = approved
        changed_ids.append(unit["id"])

    return changes, changed_ids


def apply_reviewed_xlsx(
    original: Path,
    output: Path,
    units,
    decisions_by_id,
    anchors,
):
    changes, changed_ids = _approved_changes(
        units, decisions_by_id, anchors
    )

    with zipfile.ZipFile(original, "r") as src, zipfile.ZipFile(
        output, "w"
    ) as dst:
        names = set(src.namelist())
        missing = sorted(set(changes) - names)
        if missing:
            raise XlsxExportError(
                "worksheet part missing: " + ", ".join(missing)
            )

        for info in src.infolist():
            payload = src.read(info.filename)
            if info.filename in changes:
                text = payload.decode("utf-8")
                for cell_ref, replacement in changes[
                    info.filename
                ].items():
                    text = _patch_cell(
                        text, cell_ref, replacement
                    )
                payload = text.encode("utf-8")

            # Keep the original ZipInfo metadata/compression policy.
            dst.writestr(info, payload)

    return changed_ids


def round_trip_verify_xlsx(
    output: Path,
    units,
    decisions_by_id,
    anchors,
):
    _changes, _ = _approved_changes(
        units, decisions_by_id, anchors
    )
    by_id = {unit["id"]: unit for unit in units}

    with zipfile.ZipFile(output, "r") as zf:
        shared = _shared_strings(zf)
        cache = {}

        for unit_id, anchor in anchors.items():
            if unit_id not in by_id or unit_id not in decisions_by_id:
                continue

            decision = decisions_by_id[unit_id]
            if decision.get("status") not in COMPLETED:
                continue

            approved = str(
                decision.get(
                    "approved_target",
                    by_id[unit_id].get("current_target", ""),
                )
            )
            if approved == str(
                by_id[unit_id].get("current_target") or ""
            ):
                continue

            part = anchor["part"]
            cell = anchor["cell"]
            if part not in cache:
                cache[part] = _cell_map(zf.read(part))

            actual = _cell_text(cache[part][cell], shared)
            if actual != approved:
                raise XlsxExportError(
                    "{} round-trip mismatch: expected {!r}, got {!r}".format(
                        unit_id, approved, actual
                    )
                )

    return ["Approved XLSX cell text round-trip verified"]


def _mask_cells(xml_text: str, refs):
    for ref in sorted(refs):
        xml_text, count = _cell_pattern(ref).subn(
            '<c r="{}">DBABEL_REVIEW_CELL</c>'.format(ref),
            xml_text,
        )
        if count != 1:
            raise XlsxExportError(
                "{} could not be masked for fidelity check".format(ref)
            )
    return xml_text


def verify_package_fidelity_xlsx(
    original: Path,
    output: Path,
    units,
    decisions_by_id,
    anchors,
):
    changes, _ = _approved_changes(
        units, decisions_by_id, anchors
    )

    with zipfile.ZipFile(original, "r") as src, zipfile.ZipFile(
        output, "r"
    ) as dst:
        src_names = src.namelist()
        dst_names = dst.namelist()

        if src_names != dst_names:
            raise XlsxExportError(
                "XLSX ZIP entry set/order changed"
            )

        for name in src_names:
            before = src.read(name)
            after = dst.read(name)

            if name not in changes:
                if before != after:
                    raise XlsxExportError(
                        "untouched XLSX part payload changed: " + name
                    )
                continue

            before_text = _mask_cells(
                before.decode("utf-8"),
                changes[name].keys(),
            )
            after_text = _mask_cells(
                after.decode("utf-8"),
                changes[name].keys(),
            )
            if before_text != after_text:
                raise XlsxExportError(
                    "worksheet changed outside approved cell elements: "
                    + name
                )

    return [
        "All untouched XLSX OOXML part payloads are byte-identical",
        (
            "Modified worksheets differ only inside approved anchored "
            "cell elements"
        ),
        (
            "Relationships, media, drawings, charts, comments, styles "
            "and other untouched OOXML parts remain unchanged"
        ),
    ]

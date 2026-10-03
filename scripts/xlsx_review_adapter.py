#!/usr/bin/env python3
"""Loss-minimizing XLSX review adapter for DBabel.

Only explicitly approved anchored worksheet cells and worksheet tab names are
modified. Untouched OOXML package parts are preserved byte-for-byte. Formula
cells fail closed and are never rewritten.
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
SHEET_LOCATION_RE = re.compile(r"^xl/workbook\.xml:sheet:([1-9][0-9]*)$")
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
    match = SHEET_LOCATION_RE.fullmatch(location)
    if match:
        return "xl/workbook.xml", "sheet:" + match.group(1)
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


def _sheet_map(xml_bytes: bytes) -> Dict[str, str]:
    root = ET.fromstring(xml_bytes)
    return {
        str(sheet.get("sheetId")): str(sheet.get("name") or "")
        for sheet in root.findall(".//m:sheets/m:sheet", NS)
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

            cells = _sheet_map(zf.read(part)) if part == "xl/workbook.xml" else _cell_map(zf.read(part))
            for unit, cell_ref in items:
                cell = cells.get(cell_ref.removeprefix("sheet:")) if part == "xl/workbook.xml" else cells.get(cell_ref)
                if cell is None:
                    reason = "sheet or cell not found"
                    actual = None
                else:
                    try:
                        actual = cell if part == "xl/workbook.xml" else _cell_text(cell, shared)
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


def _patch_sheet(xml_text: str, sheet_id: str, replacement: str) -> str:
    if (not replacement or len(replacement) > 31 or
            any(char in replacement for char in '[]:*?/\\') or
            replacement[0] == "'" or replacement[-1] == "'"):
        raise XlsxExportError("invalid Excel worksheet name: " + repr(replacement))
    tags = list(re.finditer(r"<sheet\b[^>]*>", xml_text))
    matches = [m for m in tags if re.search(r'\bsheetId=["\']' + re.escape(sheet_id) + r'["\']', m.group(0))]
    if len(matches) != 1:
        raise XlsxExportError("worksheet tab anchor is missing or ambiguous: " + sheet_id)
    match = matches[0]
    tag = match.group(0)
    name_match = re.search(r'\bname=(["\'])(.*?)\1', tag)
    if name_match is None:
        raise XlsxExportError("worksheet tab has no name: " + sheet_id)
    old = html.unescape(name_match.group(2))
    escaped = html.escape(replacement, quote=True)
    new_tag = tag[:name_match.start(2)] + escaped + tag[name_match.end(2):]
    xml_text = xml_text[:match.start()] + new_tag + xml_text[match.end():]
    # Excel stores print areas and titles as defined names with sheet-name
    # prefixes. Update those references without changing their coordinates.
    def replace_defined_name(m):
        body = m.group(2)
        quoted = "'" + old.replace("'", "''") + "'!"
        bare = old + "!"
        if body.startswith(quoted):
            prefix = quoted
        elif body.startswith(bare):
            prefix = bare
        else:
            return m.group(0)
        new_prefix = "'" + replacement.replace("'", "''") + "'!"
        return m.group(1) + new_prefix + body[len(prefix):] + m.group(3)
    xml_text = re.sub(r'(<definedName\b[^>]*>)(.*?)(</definedName>)', replace_defined_name, xml_text, flags=re.S)
    return xml_text


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


def _patched_payload(name: str, payload: bytes, changes: Dict[str, Dict[str, str]]) -> bytes:
    if name not in changes:
        return payload
    text = payload.decode("utf-8")
    for anchor, replacement in changes[name].items():
        if name == "xl/workbook.xml":
            text = _patch_sheet(text, anchor.removeprefix("sheet:"), replacement)
        else:
            text = _patch_cell(text, anchor, replacement)
    if name == "xl/workbook.xml":
        names = list(_sheet_map(text.encode("utf-8")).values())
        if len(names) != len({value.casefold() for value in names}):
            raise XlsxExportError("translated worksheet names must be unique")
    return text.encode("utf-8")


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

        if "xl/workbook.xml" in changes:
            old_names = _sheet_map(src.read("xl/workbook.xml"))
            for anchor in changes["xl/workbook.xml"]:
                old = old_names.get(anchor.removeprefix("sheet:"), "")
                for name in names:
                    if not re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name):
                        continue
                    root = ET.fromstring(src.read(name))
                    for formula in root.findall(".//m:f", NS):
                        if old and old in (formula.text or ""):
                            raise XlsxExportError("worksheet formula refers to a renamed tab: " + old)

        for info in src.infolist():
            payload = _patched_payload(info.filename, src.read(info.filename), changes)

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
                cache[part] = _sheet_map(zf.read(part)) if part == "xl/workbook.xml" else _cell_map(zf.read(part))

            actual = cache[part][cell.removeprefix("sheet:")] if part == "xl/workbook.xml" else _cell_text(cache[part][cell], shared)
            if actual != approved:
                raise XlsxExportError(
                    "{} round-trip mismatch: expected {!r}, got {!r}".format(
                        unit_id, approved, actual
                    )
                )

    return ["Approved XLSX cell and worksheet tab text round-trip verified"]


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

            if _patched_payload(name, before, changes) != after:
                raise XlsxExportError("XLSX part changed outside approved anchors: " + name)

    return [
        "All untouched XLSX OOXML part payloads are byte-identical",
        (
            "Modified worksheet cells and tab names match approved anchors"
        ),
        (
            "Relationships, media, drawings, charts, comments, styles "
            "and other untouched OOXML parts remain unchanged"
        ),
    ]

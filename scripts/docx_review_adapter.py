#!/usr/bin/env python3
"""Fail-closed DOCX text anchor and export adapter for DBabel Review Workbench.

The adapter patches existing OOXML text nodes instead of rebuilding the document.
Only .docx is supported. Macro-enabled packages are intentionally rejected.
"""

from __future__ import annotations

import copy
import difflib
import hashlib
import json
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from xml.etree import ElementTree as ET

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"
W14_PARA_ID = "{%s}paraId" % W14_NS
W_P = "{%s}p" % W_NS
W_T = "{%s}t" % W_NS

PART_RE = re.compile(
    r"^word/(?:document|header\d+|footer\d+|footnotes|endnotes|comments)\.xml$"
)


class DocxExportError(RuntimeError):
    pass


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _supported_docx(path: Path) -> None:
    suffix = path.suffix.lower()
    if suffix != ".docx":
        raise DocxExportError("native adapter supports .docx only, got {}".format(suffix or "<none>"))


def _iter_supported_parts(zf: zipfile.ZipFile) -> List[str]:
    return sorted(name for name in zf.namelist() if PART_RE.match(name))


def _parse_part(data: bytes) -> ET.Element:
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise DocxExportError("invalid OOXML XML part: {}".format(exc))


def _paragraph_text_nodes(paragraph: ET.Element) -> List[ET.Element]:
    return list(paragraph.iter(W_T))


def _visible_text(paragraph: ET.Element) -> str:
    return "".join(node.text or "" for node in _paragraph_text_nodes(paragraph))


def extract_paragraphs(path: Path) -> List[Dict[str, Any]]:
    _supported_docx(path)
    rows: List[Dict[str, Any]] = []
    with zipfile.ZipFile(path, "r") as zf:
        for part in _iter_supported_parts(zf):
            root = _parse_part(zf.read(part))
            ordinal = 0
            for paragraph in root.iter(W_P):
                text = _visible_text(paragraph)
                if not text:
                    ordinal += 1
                    continue
                rows.append({
                    "part": part,
                    "paragraph_ordinal": ordinal,
                    "para_id": paragraph.get(W14_PARA_ID),
                    "text": text,
                    "text_sha256": _sha_text(text),
                    "text_node_count": len(_paragraph_text_nodes(paragraph)),
                })
                ordinal += 1
    return rows


def _parse_location_hint(location: str) -> Optional[Tuple[str, int]]:
    # Canonical hint emitted by DBabel: docx:word/document.xml:p=12
    m = re.fullmatch(r"docx:(word/[^:]+\.xml):p=(\d+)", location or "")
    if not m:
        return None
    return m.group(1), int(m.group(2))


def build_anchors(path: Path, units: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    paragraphs = extract_paragraphs(path)
    by_text: Dict[str, List[Dict[str, Any]]] = {}
    by_key: Dict[Tuple[str, int], Dict[str, Any]] = {}
    for row in paragraphs:
        by_text.setdefault(row["text"], []).append(row)
        by_key[(row["part"], row["paragraph_ordinal"])] = row

    anchors: Dict[str, Dict[str, Any]] = {}
    for unit in units:
        unit_id = unit["id"]
        target = str(unit.get("current_target") or "")
        hinted = _parse_location_hint(str(unit.get("location") or ""))
        candidates: List[Dict[str, Any]] = []
        if hinted and hinted in by_key and by_key[hinted]["text"] == target:
            candidates = [by_key[hinted]]
        else:
            candidates = by_text.get(target, [])

        if len(candidates) == 1:
            row = candidates[0]
            anchor_id = "A_{}".format(unit_id)
            anchors[unit_id] = {
                "id": anchor_id,
                "unit_id": unit_id,
                "status": "RESOLVED",
                "part": row["part"],
                "paragraph_ordinal": row["paragraph_ordinal"],
                "para_id": row.get("para_id"),
                "original_text": target,
                "original_text_sha256": row["text_sha256"],
                "text_node_count": row["text_node_count"],
            }
            unit["anchor_ref"] = anchor_id
        elif len(candidates) == 0:
            anchors[unit_id] = {
                "id": "A_{}".format(unit_id),
                "unit_id": unit_id,
                "status": "UNRESOLVED",
                "reason": "current_target not found as an exact DOCX paragraph",
                "original_text": target,
            }
        else:
            anchors[unit_id] = {
                "id": "A_{}".format(unit_id),
                "unit_id": unit_id,
                "status": "AMBIGUOUS",
                "reason": "current_target occurs in {} DOCX paragraphs".format(len(candidates)),
                "original_text": target,
                "candidates": [
                    {"part": x["part"], "paragraph_ordinal": x["paragraph_ordinal"]}
                    for x in candidates
                ],
            }
    return anchors


def _set_node_text(node: ET.Element, value: str) -> None:
    node.text = value
    key = "{%s}space" % XML_NS
    if value.startswith(" ") or value.endswith(" "):
        node.set(key, "preserve")
    elif key in node.attrib:
        del node.attrib[key]


def _find_position(texts: Sequence[str], pos: int, prefer_previous: bool = False) -> Tuple[int, int]:
    total = sum(len(x) for x in texts)
    if pos < 0 or pos > total:
        raise DocxExportError("text position {} outside paragraph length {}".format(pos, total))
    if not texts:
        raise DocxExportError("paragraph has no text nodes")
    cursor = 0
    for index, text in enumerate(texts):
        end = cursor + len(text)
        if pos < end:
            return index, pos - cursor
        if pos == end:
            if prefer_previous or index == len(texts) - 1:
                return index, len(text)
            return index + 1, 0
        cursor = end
    return len(texts) - 1, len(texts[-1])


def _replace_span(texts: List[str], start: int, end: int, replacement: str) -> None:
    if start == end:
        index, offset = _find_position(texts, start, prefer_previous=True)
        texts[index] = texts[index][:offset] + replacement + texts[index][offset:]
        return
    si, so = _find_position(texts, start)
    ei, eo = _find_position(texts, end, prefer_previous=True)
    if si == ei:
        texts[si] = texts[si][:so] + replacement + texts[si][eo:]
        return
    prefix = texts[si][:so]
    suffix = texts[ei][eo:]
    texts[si] = prefix + replacement
    for idx in range(si + 1, ei):
        texts[idx] = ""
    texts[ei] = suffix


def patch_text_nodes(nodes: Sequence[ET.Element], old: str, new: str) -> None:
    original = [node.text or "" for node in nodes]
    if "".join(original) != old:
        raise DocxExportError("anchor text changed before patch")
    texts = list(original)
    matcher = difflib.SequenceMatcher(a=old, b=new, autojunk=False)
    operations = [op for op in matcher.get_opcodes() if op[0] != "equal"]
    # Reverse keeps old-string positions stable for yet-unapplied earlier edits.
    for tag, i1, i2, j1, j2 in reversed(operations):
        _replace_span(texts, i1, i2, new[j1:j2])
    if "".join(texts) != new:
        raise DocxExportError("internal text patch did not produce requested target")
    for node, value in zip(nodes, texts):
        _set_node_text(node, value)


def _paragraph_by_ordinal(root: ET.Element, ordinal: int) -> ET.Element:
    current = 0
    for paragraph in root.iter(W_P):
        if current == ordinal:
            return paragraph
        current += 1
    raise DocxExportError("paragraph ordinal {} no longer exists".format(ordinal))


def _paragraph_by_anchor(
    root: ET.Element,
    anchor: Dict[str, Any],
) -> ET.Element:
    para_id = anchor.get("para_id")

    if para_id:
        matches = [
            paragraph
            for paragraph in root.iter(W_P)
            if paragraph.get(W14_PARA_ID) == para_id
        ]

        if len(matches) == 1:
            return matches[0]

        if len(matches) > 1:
            raise DocxExportError(
                "duplicate w14:paraId in DOCX part: {}".format(
                    para_id
                )
            )

    return _paragraph_by_ordinal(
        root,
        int(anchor["paragraph_ordinal"]),
    )


def _paragraph_identity(row: Dict[str, Any]) -> Tuple[str, str]:
    para_id = row.get("para_id")

    if para_id:
        return (
            row["part"],
            "paraId:{}".format(para_id),
        )

    return (
        row["part"],
        "ordinal:{}".format(row["paragraph_ordinal"]),
    )


def _anchor_identity(anchor: Dict[str, Any]) -> Tuple[str, str]:
    para_id = anchor.get("para_id")

    if para_id:
        return (
            anchor["part"],
            "paraId:{}".format(para_id),
        )

    return (
        anchor["part"],
        "ordinal:{}".format(anchor["paragraph_ordinal"]),
    )


def _serialize_xml(root: ET.Element) -> bytes:
    # Keep familiar namespace prefixes in rewritten OOXML parts.
    ET.register_namespace("w", W_NS)
    ET.register_namespace("w14", W14_NS)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def apply_reviewed_docx(
    original: Path,
    output: Path,
    units: Sequence[Dict[str, Any]],
    decisions_by_id: Dict[str, Dict[str, Any]],
    anchors: Dict[str, Dict[str, Any]],
) -> List[str]:
    _supported_docx(original)
    if output.resolve() == original.resolve():
        raise DocxExportError("refusing to overwrite original DOCX")
    units_by_id = {x["id"]: x for x in units}
    edits: Dict[str, List[Tuple[Dict[str, Any], str, str]]] = {}
    changed_units: List[str] = []
    for unit_id, unit in units_by_id.items():
        decision = decisions_by_id[unit_id]
        if decision.get("status") not in {"ACCEPT_SUGGESTION", "KEEP_CURRENT", "USER_EDITED", "WAIVED"}:
            raise DocxExportError("unit {} is not export-approved".format(unit_id))
        final = str(decision.get("approved_target", ""))
        current = str(unit.get("current_target") or "")
        if final == current:
            continue
        anchor = anchors.get(unit_id)
        if not anchor or anchor.get("status") != "RESOLVED":
            raise DocxExportError("unit {} has no uniquely resolved DOCX anchor".format(unit_id))
        edits.setdefault(anchor["part"], []).append((anchor, current, final))
        changed_units.append(unit_id)

    with zipfile.ZipFile(original, "r") as zin, zipfile.ZipFile(output, "w") as zout:
        replacement_parts: Dict[str, bytes] = {}
        for part, part_edits in edits.items():
            if part not in zin.namelist():
                raise DocxExportError("OOXML part disappeared: {}".format(part))
            root = _parse_part(zin.read(part))
            seen_anchors = set()
            for anchor, current, final in part_edits:
                ordinal = int(anchor["paragraph_ordinal"])
                anchor_key = _anchor_identity(anchor)

                if anchor_key in seen_anchors:
                    raise DocxExportError(
                        "multiple review units target the same paragraph: {}".format(
                            anchor_key
                        )
                    )

                seen_anchors.add(anchor_key)
                paragraph = _paragraph_by_anchor(root, anchor)
                actual = _visible_text(paragraph)
                if _sha_text(actual) != anchor["original_text_sha256"] or actual != current:
                    raise DocxExportError("DOCX anchor changed for {}#{}".format(part, ordinal))
                nodes = _paragraph_text_nodes(paragraph)
                patch_text_nodes(nodes, current, final)
                if _visible_text(paragraph) != final:
                    raise DocxExportError("post-patch text mismatch for {}#{}".format(part, ordinal))
            replacement_parts[part] = _serialize_xml(root)

        for info in zin.infolist():
            data = replacement_parts.get(info.filename, zin.read(info.filename))
            cloned = copy.copy(info)
            zout.writestr(cloned, data)

    return changed_units


def round_trip_verify(
    output: Path,
    units: Sequence[Dict[str, Any]],
    decisions_by_id: Dict[str, Dict[str, Any]],
    anchors: Dict[str, Dict[str, Any]],
) -> List[str]:
    checks: List[str] = []
    with zipfile.ZipFile(output, "r") as zf:
        cache: Dict[str, ET.Element] = {}
        for unit in units:
            unit_id = unit["id"]
            decision = decisions_by_id[unit_id]
            final = str(decision.get("approved_target", unit.get("current_target") or ""))
            current = str(unit.get("current_target") or "")
            if final == current:
                continue
            anchor = anchors.get(unit_id)
            if not anchor or anchor.get("status") != "RESOLVED":
                raise DocxExportError("cannot verify unresolved anchor for {}".format(unit_id))
            part = anchor["part"]
            if part not in cache:
                cache[part] = _parse_part(zf.read(part))
            paragraph = _paragraph_by_anchor(
                cache[part],
                anchor,
            )
            actual = _visible_text(paragraph)
            if actual != final:
                raise DocxExportError("round-trip target mismatch for {}".format(unit_id))
            checks.append("{} target text matches approved decision".format(unit_id))
    return checks



def verify_non_target_text_unchanged(
    original: Path,
    output: Path,
    anchors: Dict[str, Dict[str, Any]],
    decisions_by_id: Dict[str, Dict[str, Any]],
    units: Sequence[Dict[str, Any]],
) -> List[str]:
    before = {
        _paragraph_identity(x): x["text"]
        for x in extract_paragraphs(original)
    }
    after = {
        _paragraph_identity(x): x["text"]
        for x in extract_paragraphs(output)
    }
    if set(before) != set(after):
        raise DocxExportError("DOCX paragraph structure changed during export")
    changed_keys = set()
    for unit in units:
        decision = decisions_by_id[unit["id"]]
        final = str(decision.get("approved_target", unit.get("current_target") or ""))
        current = str(unit.get("current_target") or "")
        if final == current:
            continue
        anchor = anchors.get(unit["id"]) or {}
        if anchor.get("status") == "RESOLVED":
            changed_keys.add(_anchor_identity(anchor))
    for key in sorted(before):
        if key in changed_keys:
            continue
        if before[key] != after[key]:
            raise DocxExportError(
                "non-target paragraph text changed at {}#{}".format(
                    key[0],
                    key[1],
                )
            )
    return ["non-target DOCX paragraph text remained unchanged"]

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("docx")
    parser.add_argument("--paragraphs", action="store_true", help="Print extracted paragraphs as JSON")
    args = parser.parse_args()
    path = Path(args.docx)
    rows = extract_paragraphs(path)
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Exchange plain TMX 1.4 segments without importing human approval.

Inline XML and unsupported extensions are retained in the candidate receipt and
require review; they are never flattened into a translation-memory match.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Dict, Iterable, Optional
from version_info import PACKAGE_VERSION

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MAX_INPUT_BYTES = 16 * 1024 * 1024
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
RECORD_PROPERTY = "x-dbabel-record"


def _etree():
    try:
        from lxml import etree
    except ImportError as exc:
        raise ValueError("TMX exchange requires the optional lxml dependency") from exc
    return etree


def _read(path: Path) -> bytes:
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError("TMX input exceeds the 16 MiB document intake limit")
    return raw


def _xml(node) -> str:
    return _etree().tostring(node, encoding="unicode", with_tail=False)


def import_tmx(path: Path, source_language: str, target_language: str) -> Dict[str, Any]:
    """Return unapproved candidates for one exact language pair; never write memory."""
    if not source_language.strip() or not target_language.strip():
        raise ValueError("Specify both source and target languages")
    if source_language.casefold() == target_language.casefold():
        raise ValueError("Source and target languages must differ")
    etree = _etree()
    raw = _read(path)
    parser = etree.XMLParser(resolve_entities=False, no_network=True,
                             load_dtd=False, recover=False, huge_tree=False)
    try:
        root = etree.fromstring(raw, parser)
    except etree.XMLSyntaxError as exc:
        raise ValueError("Invalid TMX XML: {}".format(exc)) from exc
    dtd = root.getroottree().docinfo.internalDTD
    if dtd is not None and list(dtd.entities()):
        raise ValueError("TMX entity declarations are unsupported")
    if root.tag != "tmx" or root.get("version") != "1.4":
        raise ValueError("Only unnamespaced TMX version 1.4 is supported")
    if len(root.findall("header")) != 1 or len(root.findall("body")) != 1:
        raise ValueError("TMX requires exactly one header and body")
    if any(child.tag not in {"header", "body"} for child in root if isinstance(child.tag, str)):
        raise ValueError("Unsupported TMX root extension")
    file_digest = hashlib.sha256(raw).hexdigest()
    body = root.find("body")
    if any(child.tag != "tu" for child in body if isinstance(child.tag, str)):
        raise ValueError("Unsupported TMX body extension")
    candidates = []
    for index, unit in enumerate(body.findall("tu"), 1):
        warnings = []
        variants = unit.findall("tuv")
        selected = []
        for requested in (source_language, target_language):
            matching = [v for v in variants
                        if str(v.get(XML_LANG) or v.get("lang") or "").casefold() == requested.casefold()]
            if len(matching) != 1:
                warnings.append("{}: expected one exact language variant; found {}".format(requested, len(matching)))
                selected.append(None)
            else:
                selected.append(matching[0])
        texts = []
        segment_xml = []
        for variant in selected:
            segments = variant.findall("seg") if variant is not None else []
            if len(segments) != 1:
                warnings.append("Each selected language variant requires exactly one seg")
                texts.append(None)
                segment_xml.append(None)
            else:
                segment = segments[0]
                segment_xml.append(_xml(segment))
                if len(segment):
                    warnings.append("Inline XML is retained; plain-segment import is unavailable")
                    texts.append(None)
                else:
                    texts.append(segment.text or "")
                    if not (segment.text or "").strip():
                        warnings.append("Empty segment requires review")
            if variant is not None and any(c.tag not in {"seg", "prop", "note"}
                                           for c in variant if isinstance(c.tag, str)):
                warnings.append("Unsupported language-variant extension is retained")
        if any(c.tag not in {"tuv", "prop", "note"}
               for c in unit if isinstance(c.tag, str)):
            warnings.append("Unsupported translation-unit extension is retained")
        dbabel_props = [p for p in unit.findall("prop") if p.get("type") == RECORD_PROPERTY]
        metadata: Dict[str, Any] = {}
        if len(dbabel_props) > 1:
            warnings.append("Duplicate DBabel metadata properties")
        elif dbabel_props:
            try:
                metadata = json.loads(dbabel_props[0].text or "")
                if not isinstance(metadata, dict):
                    raise ValueError("metadata must be an object")
            except (ValueError, TypeError):
                metadata = {}
                warnings.append("Invalid DBabel metadata is retained as XML")
        scope = metadata.get("scope", {})
        if not isinstance(scope, dict):
            scope = {}
            warnings.append("Invalid scope metadata requires review")
        text_role = metadata.get("text_role", "UNKNOWN")
        if not isinstance(text_role, str) or not text_role.strip():
            text_role = "UNKNOWN"
            warnings.append("Invalid text-role metadata requires review")
        candidates.append({
            "id": "tmx_{}_{}".format(file_digest[:16], index),
            "source_language": source_language, "target_language": target_language,
            "source": texts[0], "target": texts[1], "text_role": text_role,
            "scope": scope, "approval": "USER_REVIEW",
            "candidate_status": "UNSUPPORTED" if warnings else "REVIEW",
            "warnings": sorted(set(warnings)), "upstream_metadata": metadata,
            "provenance": {"format": "TMX_1.4", "path": str(Path(path).resolve()),
                           "sha256": file_digest, "tu_id": unit.get("tuid"),
                           "tu_index": index, "unit_xml": _xml(unit),
                           "segment_xml": segment_xml,
                           "language_tags": [v.get(XML_LANG) or v.get("lang") if v is not None else None
                                             for v in selected]},
        })
    return {"format_version": "1.0", "report_type": "TMX_IMPORT_CANDIDATES",
            "source_sha256": file_digest, "source_language": source_language,
            "target_language": target_language, "candidates": candidates,
            "counts": {"total": len(candidates),
                       "review": sum(c["candidate_status"] == "REVIEW" for c in candidates),
                       "unsupported": sum(c["candidate_status"] == "UNSUPPORTED" for c in candidates)},
            "header_xml": _xml(root.find("header")), "root_attributes": dict(root.attrib),
            "memory_changes": 0,
            "limitations": ["Imported records are unapproved candidates; no human decision or local memory is changed.",
                            "Only plain segments for the exact requested language tags can be proposed.",
                            "Inline XML and extension metadata are retained in provenance for separate review."]}


def export_tmx(entries: Iterable[Dict[str, Any]]) -> bytes:
    """Serialize local memory records with DBabel scope and original decision metadata."""
    etree = _etree()
    root = etree.Element("tmx", version="1.4")
    etree.SubElement(root, "header", creationtool="DBabel", creationtoolversion=PACKAGE_VERSION,
                     segtype="block", o_tmf="DBabel", adminlang="en", srclang="*all*", datatype="PlainText")
    body = etree.SubElement(root, "body")
    for index, entry in enumerate(entries, 1):
        if not isinstance(entry, dict):
            raise ValueError("Memory entries must be objects")
        for field in ("source", "target", "source_language", "target_language"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                raise ValueError("Memory entry requires nonempty {}".format(field))
        if entry["source_language"].casefold() == entry["target_language"].casefold():
            raise ValueError("Memory source and target languages must differ")
        unit = etree.SubElement(body, "tu", tuid="dbabel-{}".format(index))
        metadata = {k: v for k, v in entry.items()
                    if k not in {"source", "target", "source_language", "target_language"}}
        prop = etree.SubElement(unit, "prop", type=RECORD_PROPERTY)
        prop.text = json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        for language, text in ((entry["source_language"], entry["source"]),
                               (entry["target_language"], entry["target"])):
            variant = etree.SubElement(unit, "tuv", attrib={XML_LANG: language})
            segment = etree.SubElement(variant, "seg", attrib={XML_SPACE: "preserve"})
            segment.text = text
    return etree.tostring(root, encoding="UTF-8", xml_declaration=True, pretty_print=True)


def _write_new(path: Path, raw: bytes) -> None:
    with Path(path).open("xb") as stream:
        stream.write(raw)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    importer = commands.add_parser("import", help="Write unapproved candidate JSON; never update memory")
    importer.add_argument("input", type=Path)
    importer.add_argument("--source-language", required=True)
    importer.add_argument("--target-language", required=True)
    importer.add_argument("--output", required=True, type=Path)
    exporter = commands.add_parser("export", help="Export local memory or an explicit JSON entry list")
    source = exporter.add_mutually_exclusive_group(required=True)
    source.add_argument("--memory", action="store_true")
    source.add_argument("--entries", type=Path)
    exporter.add_argument("--output", required=True, type=Path)
    exporter.add_argument("--include-rejected", action="store_true",
                          help="Include rejected records as DBabel metadata; other CAT tools may ignore that status")
    args = parser.parse_args(argv)
    try:
        if args.command == "import":
            result = import_tmx(args.input, args.source_language, args.target_language)
            _write_new(args.output, (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
            print(json.dumps({"status": "CANDIDATES_CREATED", "counts": result["counts"], "memory_changes": 0}))
        else:
            if args.memory:
                from runtime.translation_memory import export_entries
                entries = export_entries()
            else:
                entries = json.loads(_read(args.entries))
                if not isinstance(entries, list):
                    raise ValueError("--entries requires a JSON array of memory records")
            selected = entries if args.include_rejected else [e for e in entries if isinstance(e, dict) and e.get("kind") != "REJECTED"]
            if any(not isinstance(e, dict) for e in entries):
                raise ValueError("Memory entries must be objects")
            _write_new(args.output, export_tmx(selected))
            print(json.dumps({"status": "EXPORTED", "entries": len(selected),
                              "excluded_rejected_entries": len(entries) - len(selected)}))
    except (ValueError, OSError, TypeError) as exc:
        print("TMX exchange failed: {}".format(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

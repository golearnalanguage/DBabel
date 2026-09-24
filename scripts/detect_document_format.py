#!/usr/bin/env python3
"""Bounded, non-executing document-format probe for DBabel."""
import argparse
import csv
import io
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from jsonschema import Draft202012Validator

from format_registry import declared_format, format_spec, load_registry

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "document_probe.schema.json"

OLE_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"
GIF87 = b"GIF87a"
GIF89 = b"GIF89a"
TIFF_LE = b"II*\x00"
TIFF_BE = b"MM\x00*"
BMP_MAGIC = b"BM"
PDF_MAGIC = b"%PDF-"
ZIP_MAGICS = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")


class ProbeError(ValueError):
    pass


def _validate_report(report: dict) -> List[str]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    return [
        "schema {}: {}".format(
            ".".join(str(x) for x in err.absolute_path) or "<root>", err.message
        )
        for err in validator.iter_errors(report)
    ]


def _read_bounded(path: Path, limit: int) -> bytes:
    with path.open("rb") as handle:
        return handle.read(limit)


def _safe_zip_read(zf: zipfile.ZipFile, name: str, limit: int) -> bytes:
    try:
        info = zf.getinfo(name)
    except KeyError:
        return b""
    if info.file_size > limit:
        return b""
    with zf.open(info, "r") as handle:
        return handle.read(limit + 1)[:limit]


def _zip_probe(path: Path, registry: dict) -> Tuple[str, str, bool, List[str], List[str]]:
    limits = registry["probe"]
    max_members = int(limits["max_zip_members"])
    max_meta = int(limits["max_zip_metadata_bytes"])
    evidence: List[str] = []
    risks: List[str] = []

    try:
        with zipfile.ZipFile(str(path), "r") as zf:
            infos = zf.infolist()
            if len(infos) > max_members:
                raise ProbeError(
                    "ZIP contains {} members, exceeding probe limit {}".format(
                        len(infos), max_members
                    )
                )
            names = {info.filename.replace("\\", "/").lower() for info in infos}
            evidence.append("ZIP central directory inspected: {} members".format(len(infos)))

            content_types = _safe_zip_read(zf, "[Content_Types].xml", max_meta).lower()
            mimetype = _safe_zip_read(zf, "mimetype", max_meta).decode(
                "utf-8", errors="replace"
            ).strip()

            macro = any(name.endswith("vbaproject.bin") for name in names)
            if macro:
                evidence.append("VBA project member present")

            if "word/document.xml" in names:
                is_macro = macro or b"macroenabled" in content_types
                evidence.append("OOXML Word package marker word/document.xml present")
                return ("docm" if is_macro else "docx", "zip", is_macro, risks, evidence)
            if "ppt/presentation.xml" in names:
                is_macro = macro or b"macroenabled" in content_types
                evidence.append("OOXML PowerPoint package marker ppt/presentation.xml present")
                return ("pptm" if is_macro else "pptx", "zip", is_macro, risks, evidence)
            if "xl/workbook.xml" in names:
                is_macro = macro or b"macroenabled" in content_types
                evidence.append("OOXML Excel package marker xl/workbook.xml present")
                return ("xlsm" if is_macro else "xlsx", "zip", is_macro, risks, evidence)

            odf_map = {
                "application/vnd.oasis.opendocument.text": "odt",
                "application/vnd.oasis.opendocument.spreadsheet": "ods",
                "application/vnd.oasis.opendocument.presentation": "odp",
            }
            if mimetype in odf_map:
                evidence.append("ODF mimetype member: {}".format(mimetype))
                return (odf_map[mimetype], "zip", False, risks, evidence)
            if mimetype == "application/epub+zip" or "meta-inf/container.xml" in names:
                evidence.append("EPUB package marker present")
                return ("epub", "zip", False, risks, evidence)

            risks.append("GENERIC_ARCHIVE")
            return ("zip", "zip", False, risks, evidence)
    except zipfile.BadZipFile as exc:
        raise ProbeError("ZIP signature present but archive metadata is invalid: {}".format(exc))


def _looks_text(data: bytes) -> bool:
    if not data:
        return True
    if b"\x00" in data:
        return False
    sample = data[:65536]
    controls = sum(1 for b in sample if b < 9 or (13 < b < 32))
    return controls / max(len(sample), 1) < 0.02


def _text_probe(path: Path, registry: dict) -> Tuple[str, str, List[str]]:
    limit = int(registry["probe"]["max_text_probe_bytes"])
    raw = _read_bounded(path, limit + 1)
    truncated = len(raw) > limit
    raw = raw[:limit]
    evidence: List[str] = []

    if not _looks_text(raw):
        return ("unknown", "NONE", evidence)

    text = raw.decode("utf-8", errors="replace")
    stripped = text.lstrip("\ufeff\r\n\t ")
    lower = stripped[:8192].lower()

    if lower.startswith("<!doctype html") or re.search(r"<html(?:\s|>)", lower[:2048]):
        evidence.append("HTML document marker detected in text prefix")
        return ("html", "HIGH", evidence)

    if stripped.startswith("<?xml") or re.match(r"<[^!?][^>]*>", stripped[:2048]):
        evidence.append("XML-like root markup detected in text prefix")
        return ("xml", "MEDIUM", evidence)

    if not truncated and stripped[:1] in ("{", "["):
        try:
            json.loads(stripped)
            evidence.append("Entire bounded text parses as JSON")
            return ("json", "HIGH", evidence)
        except json.JSONDecodeError:
            pass

    lines = text.splitlines()
    sample = "\n".join(lines[:50])
    if len(lines) >= 2 and sample:
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            rows = list(csv.reader(io.StringIO(sample), dialect))
            widths = [len(row) for row in rows if row]
            if len(widths) >= 2 and min(widths) >= 2 and len(set(widths[:10])) <= 2:
                evidence.append("Delimited multi-row text pattern detected")
                return ("csv", "MEDIUM", evidence)
        except (csv.Error, UnicodeError):
            pass

    md_signals = 0
    for line in lines[:80]:
        if re.match(r"^#{1,6}\s+\S", line):
            md_signals += 2
        if re.match(r"^\s*[-*+]\s+\S", line):
            md_signals += 1
        if re.match(r"^\s*```", line):
            md_signals += 2
        if re.search(r"\[[^\]]+\]\([^\)]+\)", line):
            md_signals += 1
    if md_signals >= 2:
        evidence.append("Markdown structural markers detected")
        return ("md", "MEDIUM", evidence)

    evidence.append("Content is text-like without a stronger structured-text signature")
    return ("txt", "LOW", evidence)


def _plugin_hint(path: Path, backend: str) -> Optional[dict]:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    if backend == "filetype":
        from plugins.format_backends import filetype_backend as adapter
    elif backend == "python_magic":
        from plugins.format_backends import python_magic_backend as adapter
    else:
        raise ProbeError("unknown detector backend: {}".format(backend))
    return adapter.probe(path)


def probe_document(
    path: Path,
    registry: Optional[dict] = None,
    fallback_backend: str = "auto",
) -> dict:
    registry = registry or load_registry()
    path = Path(path)
    if not path.is_file():
        raise ProbeError("input is not a readable regular file: {}".format(path))

    declared = declared_format(path, registry)
    size = path.stat().st_size
    header = _read_bounded(path, int(registry["probe"]["max_header_bytes"]))
    detected = "unknown"
    confidence = "NONE"
    container: Optional[str] = None
    macro = False
    risks: List[str] = []
    evidence: List[str] = []

    if header.startswith(PDF_MAGIC):
        detected, confidence = "pdf", "HIGH"
        evidence.append("PDF magic signature %PDF- present")
    elif header.startswith(PNG_MAGIC):
        detected, confidence = "png", "HIGH"
        evidence.append("PNG magic signature present")
    elif header.startswith(JPEG_MAGIC):
        detected, confidence = "jpeg", "HIGH"
        evidence.append("JPEG magic signature present")
    elif header.startswith((GIF87, GIF89)):
        detected, confidence = "gif", "HIGH"
        evidence.append("GIF magic signature present")
    elif header.startswith((TIFF_LE, TIFF_BE)):
        detected, confidence = "tiff", "HIGH"
        evidence.append("TIFF magic signature present")
    elif header.startswith(BMP_MAGIC):
        detected, confidence = "bmp", "HIGH"
        evidence.append("BMP magic signature present")
    elif header.startswith(OLE_MAGIC):
        detected, confidence, container = "ole", "HIGH", "ole"
        evidence.append("OLE Compound File Binary signature present")
        risks.extend(["LEGACY_CONTAINER", "SUBTYPE_UNVERIFIED"])
    elif header.startswith(ZIP_MAGICS):
        detected, container, macro, zip_risks, zip_evidence = _zip_probe(path, registry)
        confidence = "HIGH"
        risks.extend(zip_risks)
        evidence.extend(zip_evidence)
    else:
        detected, confidence, text_evidence = _text_probe(path, registry)
        evidence.extend(text_evidence)

    if detected == "unknown" and fallback_backend != "none":
        candidates = [fallback_backend] if fallback_backend != "auto" else ["filetype", "python_magic"]
        for backend in candidates:
            hint = _plugin_hint(path, backend)
            if hint:
                detected = hint["format"]
                confidence = hint.get("confidence", "LOW")
                evidence.append(hint.get("evidence", "optional detector hint"))
                evidence.append("Optional detector hint used because built-in probe was inconclusive")
                break

    effective = detected
    status = "UNKNOWN"

    legacy_declared = {"doc", "xls", "ppt"}
    if detected == "ole" and declared in legacy_declared:
        effective = declared
        status = "CONTAINER_MATCH"
        confidence = "MEDIUM"
        evidence.append(
            "Legacy Office subtype derives from extension after OLE container verification"
        )
    elif detected == "unknown" and declared:
        effective = declared
        status = "EXTENSION_ONLY"
        confidence = "LOW"
        risks.append("EXTENSION_ONLY_UNVERIFIED")
        evidence.append("No content signature confirmed the extension claim")
    elif detected == "unknown" and not declared:
        effective = "unknown"
        status = "UNKNOWN"
        risks.append("UNKNOWN_FORMAT")
    elif declared is None:
        status = "CONTENT_ONLY"
    elif declared == detected:
        status = "MATCH"
    else:
        status = "CONFLICT"
        risks.append("EXTENSION_CONTENT_CONFLICT")
        evidence.append(
            "Extension claims {} but content probe identifies {}".format(declared, detected)
        )

    spec = format_spec(effective, registry)
    if spec:
        family = spec["family"]
        task_context_format = spec["task_context_format"]
        for risk in spec.get("risks", []):
            if risk not in risks:
                risks.append(risk)
    else:
        family = "unknown"
        task_context_format = "unknown"

    if macro and "MACRO_ENABLED" not in risks:
        risks.append("MACRO_ENABLED")

    report = {
        "format_version": "1.0",
        "path": str(path),
        "file_size": size,
        "declared_format": declared,
        "detected_format": detected,
        "effective_format": effective,
        "task_context_format": task_context_format,
        "family": family,
        "confidence": confidence,
        "status": status,
        "container": container,
        "macro_enabled": bool(macro),
        "risk_flags": risks,
        "evidence": evidence,
    }
    errors = _validate_report(report)
    if errors:
        raise ProbeError("generated invalid document probe: " + "; ".join(errors))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument(
        "--fallback-backend",
        choices=["auto", "none", "filetype", "python_magic"],
        default="auto",
        help="Optional detector hint used only if the built-in probe is inconclusive.",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = probe_document(args.path, fallback_backend=args.fallback_backend)
    except (OSError, ValueError, ProbeError) as exc:
        parser.exit(2, "Document probe failed: {}\n".format(exc))
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()

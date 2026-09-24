"""Optional filetype.py hint adapter. Third-party package is not bundled."""
import importlib.util
from pathlib import Path
from typing import Optional


_MAP = {
    "pdf": "pdf",
    "docx": "docx",
    "pptx": "pptx",
    "xlsx": "xlsx",
    "zip": "zip",
    "png": "png",
    "jpg": "jpeg",
    "jpeg": "jpeg",
    "gif": "gif",
    "tif": "tiff",
    "tiff": "tiff",
    "bmp": "bmp",
}


def available() -> bool:
    return importlib.util.find_spec("filetype") is not None


def probe(path: Path) -> Optional[dict]:
    if not available():
        return None
    try:
        import filetype  # type: ignore
        kind = filetype.guess(str(path))
    except Exception:
        return None
    if kind is None:
        return None
    fmt = _MAP.get(str(kind.extension).lower())
    if not fmt:
        return None
    return {
        "format": fmt,
        "confidence": "LOW",
        "evidence": "filetype.py hint: extension={} mime={}".format(
            kind.extension, kind.mime
        ),
    }

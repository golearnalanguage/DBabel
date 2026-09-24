"""Optional python-magic MIME hint adapter. Third-party package is not bundled."""
import importlib.util
from pathlib import Path
from typing import Optional


_MIME_MAP = {
    "application/pdf": "pdf",
    "application/zip": "zip",
    "application/msword": "doc",
    "application/vnd.ms-excel": "xls",
    "application/vnd.ms-powerpoint": "ppt",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "image/png": "png",
    "image/jpeg": "jpeg",
    "image/gif": "gif",
    "image/tiff": "tiff",
    "image/bmp": "bmp",
    "text/html": "html",
    "application/xml": "xml",
    "text/xml": "xml",
    "application/json": "json",
    "text/csv": "csv",
    "text/plain": "txt",
}


def available() -> bool:
    return importlib.util.find_spec("magic") is not None


def probe(path: Path) -> Optional[dict]:
    if not available():
        return None
    try:
        import magic  # type: ignore
        mime = str(magic.from_file(str(path), mime=True)).split(";", 1)[0].strip().lower()
    except Exception:
        return None
    fmt = _MIME_MAP.get(mime)
    if not fmt:
        return None
    return {
        "format": fmt,
        "confidence": "LOW",
        "evidence": "python-magic hint: mime={}".format(mime),
    }

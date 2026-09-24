#!/usr/bin/env python3
"""Combine document-format probing with backend capability selection."""
import argparse
import json
from pathlib import Path
from typing import Iterable, List, Optional

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from detect_document_format import ProbeError, probe_document
from format_registry import format_spec, load_registry
from probe_capabilities import CapabilityError, probe_capabilities

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"
SCHEMA_PATH = SCHEMA_DIR / "document_preflight.schema.json"
SCHEMA_BASE = "https://dbabel.invalid/schemas/"


class PreflightError(ValueError):
    pass


def _validate(report: dict) -> List[str]:
    schemas = {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in SCHEMA_DIR.glob("*.json")
    }
    registry = Registry().with_resources(
        (SCHEMA_BASE + name, Resource.from_contents(schema))
        for name, schema in schemas.items()
    )
    validator = Draft202012Validator(
        {"$ref": SCHEMA_BASE + "document_preflight.schema.json"},
        registry=registry,
    )
    return [
        "schema {}: {}".format(
            ".".join(str(x) for x in err.absolute_path) or "<root>", err.message
        )
        for err in validator.iter_errors(report)
    ]


def select_backend(
    probe: dict,
    capabilities: dict,
    intent: str,
    registry: dict,
) -> dict:
    if intent not in {"audit", "repair"}:
        raise PreflightError("unsupported intent: {}".format(intent))

    if probe["status"] == "CONFLICT":
        return {
            "status": "BLOCKED_FORMAT_CONFLICT",
            "candidates": [],
            "selected_backend": None,
            "reason": (
                "Declared extension and detected content disagree; parser selection is "
                "blocked until the mismatch is resolved or explicitly reclassified."
            ),
        }

    if probe["status"] in {"UNKNOWN", "EXTENSION_ONLY"}:
        return {
            "status": "BLOCKED_UNVERIFIED_FORMAT",
            "candidates": [],
            "selected_backend": None,
            "reason": "Content identity is not sufficiently verified for automatic parser selection.",
        }

    fmt = probe["effective_format"]
    spec = format_spec(fmt, registry)
    if not spec:
        return {
            "status": "NO_BACKEND",
            "candidates": [],
            "selected_backend": None,
            "reason": "Detected format has no DBabel format-registry entry.",
        }

    key = "{}_backends".format(intent)
    candidates = list(spec[key])

    if intent == "repair" and (
        "DEDICATED_REPAIR_REQUIRED" in probe["risk_flags"] or not candidates
    ):
        return {
            "status": "REPAIR_REQUIRES_DEDICATED_WORKFLOW",
            "candidates": candidates,
            "selected_backend": None,
            "reason": (
                "This format is not eligible for generic automatic repair; use a dedicated "
                "format workflow with explicit preservation and round-trip QA."
            ),
        }

    for backend in candidates:
        item = capabilities["backends"].get(backend, {})
        if item.get("available") is True:
            return {
                "status": "READY",
                "candidates": candidates,
                "selected_backend": backend,
                "reason": "Selected the first available backend in registry preference order.",
            }

    return {
        "status": "NO_BACKEND",
        "candidates": candidates,
        "selected_backend": None,
        "reason": "No registered parser backend for this format is available in the current runtime.",
    }


def preflight_document(
    path: Path,
    intent: str = "audit",
    declared_backends: Optional[Iterable[str]] = None,
    fallback_backend: str = "auto",
    registry: Optional[dict] = None,
) -> dict:
    registry = registry or load_registry()
    probe = probe_document(path, registry=registry, fallback_backend=fallback_backend)
    capabilities = probe_capabilities(declared_backends, registry=registry)
    selection = select_backend(probe, capabilities, intent, registry)
    report = {
        "format_version": "1.0",
        "intent": intent,
        "probe": probe,
        "capabilities": capabilities,
        "selection": selection,
    }
    errors = _validate(report)
    if errors:
        raise PreflightError("generated invalid preflight report: " + "; ".join(errors))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--intent", choices=["audit", "repair"], default="audit")
    parser.add_argument("--declare-backend", action="append", default=[])
    parser.add_argument(
        "--fallback-backend",
        choices=["auto", "none", "filetype", "python_magic"],
        default="auto",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        report = preflight_document(
            args.path,
            intent=args.intent,
            declared_backends=args.declare_backend,
            fallback_backend=args.fallback_backend,
        )
    except (OSError, ValueError, ProbeError, CapabilityError, PreflightError) as exc:
        parser.exit(2, "Document preflight failed: {}\n".format(exc))

    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")

    if report["selection"]["status"] != "READY":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

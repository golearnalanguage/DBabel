#!/usr/bin/env python3
"""Load and validate DBabel's local format/backend registry."""
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "config" / "format_registry.yaml"
SCHEMA_PATH = ROOT / "schemas" / "format_registry.schema.json"
TASK_CONTEXT_SCHEMA = ROOT / "schemas" / "task_context.schema.json"


class FormatRegistryError(ValueError):
    pass


def _schema_errors(data: dict) -> List[str]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    return [
        "schema {}: {}".format(
            ".".join(str(x) for x in err.absolute_path) or "<root>", err.message
        )
        for err in validator.iter_errors(data)
    ]


def _task_context_formats() -> set:
    schema = json.loads(TASK_CONTEXT_SCHEMA.read_text(encoding="utf-8"))
    return set(schema["properties"]["format"]["enum"])


def validate_registry(data: dict) -> List[str]:
    errors = _schema_errors(data)
    if errors:
        return errors

    backends = data["backends"]
    task_formats = _task_context_formats()

    for ext, fmt in data["extensions"].items():
        if fmt not in data["formats"]:
            errors.append("extension {} references unknown format {}".format(ext, fmt))

    for fmt, spec in data["formats"].items():
        if spec["task_context_format"] not in task_formats:
            errors.append(
                "format {} maps to unsupported task-context format {}".format(
                    fmt, spec["task_context_format"]
                )
            )
        for field in ("audit_backends", "repair_backends"):
            for backend in spec[field]:
                if backend not in backends:
                    errors.append(
                        "format {} {} references unknown backend {}".format(
                            fmt, field, backend
                        )
                    )
                elif backends[backend]["kind"] != "parser":
                    errors.append(
                        "format {} {} references non-parser backend {}".format(
                            fmt, field, backend
                        )
                    )

    for name, spec in backends.items():
        if spec.get("builtin") and spec.get("external"):
            errors.append("backend {} cannot be both builtin and external".format(name))
        if not spec.get("builtin") and not spec.get("external") and not spec.get("import_name"):
            errors.append(
                "backend {} must define import_name unless builtin or external".format(name)
            )
    return errors


def load_registry(path: Optional[Path] = None) -> dict:
    path = path or REGISTRY_PATH
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise FormatRegistryError("format registry root must be a mapping")
    errors = validate_registry(data)
    if errors:
        raise FormatRegistryError("; ".join(errors))
    return data


def declared_format(path: Path, registry: Optional[dict] = None) -> Optional[str]:
    registry = registry or load_registry()
    suffix = path.suffix.lower().lstrip(".")
    if not suffix:
        return None
    return registry["extensions"].get(suffix)


def format_spec(fmt: str, registry: Optional[dict] = None) -> Optional[dict]:
    registry = registry or load_registry()
    return registry["formats"].get(fmt)


def all_parser_backends(registry: Optional[dict] = None) -> Iterable[str]:
    registry = registry or load_registry()
    for name, spec in registry["backends"].items():
        if spec["kind"] == "parser":
            yield name

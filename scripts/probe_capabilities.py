#!/usr/bin/env python3
"""Report locally available DBabel format backends without importing them."""
import argparse
import importlib.metadata
import importlib.util
import json
import platform
from pathlib import Path
from typing import Iterable, List, Optional, Set, Tuple

from jsonschema import Draft202012Validator

from format_registry import load_registry

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "capability_report.schema.json"


class CapabilityError(ValueError):
    pass


def _version_tuple(value: str) -> Tuple[int, ...]:
    try:
        return tuple(int(part) for part in value.split("."))
    except ValueError:
        raise CapabilityError("invalid numeric version: {}".format(value))


def _validate(report: dict) -> List[str]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return [
        "schema {}: {}".format(
            ".".join(str(x) for x in err.absolute_path) or "<root>", err.message
        )
        for err in Draft202012Validator(schema).iter_errors(report)
    ]


def probe_capabilities(
    declared: Optional[Iterable[str]] = None,
    registry: Optional[dict] = None,
) -> dict:
    registry = registry or load_registry()
    declared_set: Set[str] = set(declared or [])
    unknown = sorted(declared_set - set(registry["backends"]))
    if unknown:
        raise CapabilityError(
            "cannot declare unknown backends: {}".format(", ".join(unknown))
        )

    current_python = platform.python_version()
    current_short = ".".join(current_python.split(".")[:2])
    current_tuple = _version_tuple(current_short)
    result = {}

    for name, spec in registry["backends"].items():
        item = {"kind": spec["kind"], "available": False, "source": "UNAVAILABLE"}
        if spec.get("upstream"):
            item["upstream"] = spec["upstream"]

        if name in declared_set:
            item["available"] = True
            item["source"] = "DECLARED"
            item["reason"] = "Capability was explicitly declared by the runtime/user."
            result[name] = item
            continue

        if spec.get("builtin"):
            item["available"] = True
            item["source"] = "BUILTIN"
            result[name] = item
            continue

        if spec.get("external"):
            item["reason"] = "External hosting-agent capability must be declared explicitly."
            result[name] = item
            continue

        minimum = spec.get("python_min")
        if minimum and current_tuple < _version_tuple(minimum):
            item["reason"] = "Runtime Python {} is below backend minimum {}.".format(
                current_short, minimum
            )
            result[name] = item
            continue

        import_name = spec.get("import_name")
        if not import_name or importlib.util.find_spec(import_name) is None:
            item["reason"] = "Python module is not installed in this runtime."
            result[name] = item
            continue

        if spec.get("external_runtime"):
            item["reason"] = (
                "Python module is present, but its external/native runtime cannot be "
                "verified safely; declare the backend explicitly after verification."
            )
            result[name] = item
            continue

        item["available"] = True
        item["source"] = "DETECTED"
        distribution = spec.get("distribution")
        if distribution:
            try:
                item["version"] = importlib.metadata.version(distribution)
            except importlib.metadata.PackageNotFoundError:
                pass
        if spec.get("external_runtime"):
            item["reason"] = (
                "Python package is present, but successful use may still require an "
                "external/native runtime."
            )
        result[name] = item

    report = {
        "format_version": "1.0",
        "python_version": current_python,
        "backends": result,
    }
    errors = _validate(report)
    if errors:
        raise CapabilityError("generated invalid capability report: " + "; ".join(errors))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--declare",
        action="append",
        default=[],
        metavar="BACKEND",
        help="Declare an external capability such as native_agent. Repeat as needed.",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = probe_capabilities(args.declare)
    except (OSError, ValueError, CapabilityError) as exc:
        parser.exit(2, "Capability probe failed: {}\n".format(exc))
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Check declared dependency pins and retain installed license/NOTICE material."""
from __future__ import annotations

import argparse
import hashlib
from importlib import metadata
import json
from pathlib import Path
import re
import shutil
import sys
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = "config/third_party_components.json"
NOTICE_NAMES = re.compile(r"^(?:licen[cs]es?|notices?|copying|copyrights?|authors|third[-_ ]?party[-_ ]?notices?)(?:[._-].*)?$", re.I)


def _key(name):
    return re.sub(r"[-_.]+", "-", name).casefold()


def _load(root):
    return json.loads((Path(root) / COMPONENTS).read_text(encoding="utf-8"))


def _pins(path):
    output = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Za-z0-9_.-]+)==([^\s;]+)", line.strip())
        if match:
            name = _key(match[1])
            if name in output:
                raise ValueError("Duplicate dependency pin: " + name)
            output[name] = match[2]
    return output


def check(root=ROOT):
    """Return machine-checkable static declaration/pin errors, without fetching sources."""
    errors = []
    try:
        declaration = _load(root)
        if set(declaration) != {"format_version", "components"} or declaration["format_version"] != "1.0":
            return [COMPONENTS + ": invalid contract"]
        components = declaration["components"]
        if not isinstance(components, list):
            return [COMPONENTS + ": components must be a list"]
        by_name = {}
        for item in components:
            required = {"name", "version", "source", "license", "kind", "usage", "original_notice"}
            if not isinstance(item, dict) or set(item) != required:
                errors.append(COMPONENTS + ": incomplete component record")
                continue
            if any(not isinstance(item[field], str) or not item[field].strip()
                   for field in ("name", "source", "license", "kind", "usage")):
                errors.append(COMPONENTS + ": component fields require nonempty strings")
                continue
            name = _key(item["name"])
            if name in by_name:
                errors.append(COMPONENTS + ": duplicate component " + name)
            by_name[name] = item
            notice = item["original_notice"]
            if (not isinstance(notice, dict) or set(notice) != {"attribution", "url"}
                    or any(not isinstance(notice[field], str) or not notice[field].strip()
                           for field in ("attribution", "url"))
                    or not notice["url"].startswith("https://")):
                errors.append(name + ": original notice attribution/source missing")
            if not item["source"].startswith("https://"):
                errors.append(name + ": source must be an HTTPS upstream URL")
            if item["kind"] not in {"runtime_optional", "dev", "reference"}:
                errors.append(name + ": unknown component kind")
            if item["kind"] == "reference":
                if item["version"] is not None:
                    errors.append(name + ": reference must not claim an installed version")
            elif not isinstance(item["version"], str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", item["version"]):
                errors.append(name + ": adopted component requires an exact version")
        runtime = _pins(Path(root) / "requirements-integration.txt")
        python_dev = _pins(Path(root) / "requirements-property.txt")
        package = json.loads((Path(root) / "package.json").read_text())
        lock = json.loads((Path(root) / "package-lock.json").read_text())
        npm_dev = package.get("devDependencies", {})
        for name, version in runtime.items():
            item = by_name.get(name)
            if not item or item["kind"] != "runtime_optional" or item["version"] != version:
                errors.append(name + ": runtime integration pin/declaration mismatch")
        for name, version in python_dev.items():
            item = by_name.get(name)
            if not item or item["kind"] != "dev" or item["version"] != version:
                errors.append(name + ": Python development pin/declaration mismatch")
        for name, version in npm_dev.items():
            item = by_name.get(_key(name))
            locked = lock.get("packages", {}).get("node_modules/" + name, {}).get("version")
            root_pin = lock.get("packages", {}).get("", {}).get("devDependencies", {}).get(name)
            if not item or item["kind"] != "dev" or item["version"] != version or locked != version or root_pin != version:
                errors.append(name + ": Node development pin/lock/declaration mismatch")
        declared = {name for name, item in by_name.items() if item["kind"] != "reference"}
        if declared != set(runtime) | set(python_dev) | {_key(name) for name in npm_dev}:
            errors.append(COMPONENTS + ": adopted component set differs from dependency files")
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        errors.append("Third-party declaration check failed: " + str(exc))
    return errors


def _retain(source, destination):
    source = Path(source)
    if not source.is_file():
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return {"path": str(destination), "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            "bytes": destination.stat().st_size}


def export_installed(output, root=ROOT, distribution_paths=None, include_node=True):
    """Inventory actual artifacts, preserving license bytes; unknown declarations need review."""
    errors = check(root)
    if errors:
        raise ValueError("; ".join(errors))
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    components = {_key(c["name"]): c for c in _load(root)["components"] if c["kind"] != "reference"}
    distributions = metadata.distributions(path=[str(p) for p in distribution_paths]) if distribution_paths else metadata.distributions()
    inventory, issues = [], []
    for install_index, distribution in enumerate(sorted(distributions, key=lambda d: (_key(d.metadata.get("Name", "")), d.version)), 1):
        name = distribution.metadata.get("Name") or "UNKNOWN"
        key = _key(name)
        if (not re.fullmatch(r"[a-z0-9][a-z0-9-]*", key)
                or not re.fullmatch(r"[A-Za-z0-9_.+!-]+", distribution.version)):
            issues.append({"name": name, "reason": "INVALID_DISTRIBUTION_NAME"})
            continue
        declared_license = distribution.metadata.get("License-Expression") or distribution.metadata.get("License")
        classifiers = [v for v in distribution.metadata.get_all("Classifier", []) if v.startswith("License ::")]
        artifact_root = Path(distribution.locate_file("")).resolve()
        materials = []
        files = sorted(distribution.files or [], key=str)
        for file in files:
            if not NOTICE_NAMES.fullmatch(Path(str(file)).name):
                continue
            source = Path(distribution.locate_file(file)).resolve()
            if not source.is_relative_to(artifact_root):
                issues.append({"name": name, "reason": "LICENSE_PATH_OUTSIDE_ARTIFACT", "file": str(file)})
                continue
            destination = output / "python" / (key + "-" + distribution.version) / str(install_index) / source.relative_to(artifact_root)
            material = _retain(source, destination)
            if material:
                material["path"] = str(destination.relative_to(output))
                material["original_path"] = str(file)
                materials.append(material)
        expected = components.get(key)
        if expected and distribution.version != expected["version"]:
            issues.append({"name": name, "reason": "INSTALLED_VERSION_MISMATCH",
                           "expected": expected["version"], "actual": distribution.version})
        expression = distribution.metadata.get("License-Expression")
        if expected and expression and expression != expected["license"]:
            issues.append({"name": name, "reason": "LICENSE_EXPRESSION_MISMATCH",
                           "declared": expected["license"], "installed": expression})
        if not any(not Path(m["original_path"]).name.upper().startswith("AUTHORS") for m in materials):
            issues.append({"name": name, "reason": "NO_LICENSE_OR_NOTICE_MATERIAL"})
        if not declared_license and not classifiers:
            issues.append({"name": name, "reason": "LICENSE_METADATA_UNKNOWN"})
        inventory.append({"ecosystem": "python", "name": name, "version": distribution.version,
                          "declared_license": declared_license, "license_classifiers": classifiers,
                          "dbabel_declaration": expected, "materials": materials})
    lock = json.loads((Path(root) / "package-lock.json").read_text())
    for relative, locked in sorted(lock.get("packages", {}).items()) if include_node else []:
        if not relative.startswith("node_modules/"):
            continue
        package_root = Path(root) / relative
        if not package_root.resolve().is_relative_to((Path(root) / "node_modules").resolve()):
            issues.append({"name": relative, "reason": "PACKAGE_PATH_OUTSIDE_ARTIFACT"})
            continue
        if not (package_root / "package.json").is_file():
            continue
        package = json.loads((package_root / "package.json").read_text())
        name, version = package.get("name", relative), package.get("version", "UNKNOWN")
        expected = components.get(_key(name))
        materials = []
        for source in sorted(package_root.iterdir()):
            if NOTICE_NAMES.fullmatch(source.name) and source.is_file():
                if not source.resolve().is_relative_to(package_root.resolve()):
                    issues.append({"name": name, "reason": "LICENSE_PATH_OUTSIDE_ARTIFACT", "file": str(source)})
                    continue
                destination = output / "node" / relative / source.name
                material = _retain(source, destination)
                material["path"] = str(destination.relative_to(output))
                material["original_path"] = str(source.relative_to(root))
                materials.append(material)
        if version != locked.get("version"):
            issues.append({"name": name, "reason": "INSTALLED_VERSION_MISMATCH", "expected": locked.get("version"), "actual": version})
        if not any(not Path(m["original_path"]).name.upper().startswith("AUTHORS") for m in materials):
            issues.append({"name": name, "reason": "NO_LICENSE_OR_NOTICE_MATERIAL"})
        if not package.get("license"):
            issues.append({"name": name, "reason": "LICENSE_METADATA_UNKNOWN"})
        elif expected and package.get("license") != expected["license"]:
            issues.append({"name": name, "reason": "LICENSE_EXPRESSION_MISMATCH",
                           "declared": expected["license"], "installed": package.get("license")})
        inventory.append({"ecosystem": "node", "name": name, "version": version,
                          "declared_license": package.get("license"),
                          "dbabel_declaration": expected, "materials": materials})
    found = {_key(item["name"]) for item in inventory}
    report = {"format_version": "1.0", "python": sys.version.split()[0], "installed": inventory,
              "not_installed": sorted(set(components) - found), "issues": issues,
              "limitations": ["Metadata licenses are retained verbatim, not inferred from project names or rewritten under DBabel's license.",
                              "Native-library declarations inside wheel LICENSES/NOTICE files remain in the retained original material.",
                              "CPython/OpenSSL standalone runtimes, browser binaries and optional backends outside these artifact roots require separate release inventory."]}
    (output / "inventory.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: Optional[list[str]] = None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installed", action="store_true")
    parser.add_argument("--distribution-path", action="append", type=Path)
    parser.add_argument("--no-node", action="store_true", help="Inventory only the selected Python distribution roots")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    errors = check()
    if errors:
        parser.exit(1, "\n".join(errors) + "\n")
    if args.installed:
        if not args.output:
            parser.error("--installed requires a new --output directory")
        try:
            report = export_installed(args.output, distribution_paths=args.distribution_path, include_node=not args.no_node)
        except (OSError, ValueError, TypeError) as exc:
            parser.exit(1, "Installed license inventory failed: {}\n".format(exc))
        print(json.dumps({"status": "REVIEW_REQUIRED" if report["issues"] else "INVENTORIED",
                          "installed": len(report["installed"]), "issues": report["issues"],
                          "output": str(args.output)}, ensure_ascii=False))
        return 2 if report["issues"] else 0
    print("Third-party declarations and exact pins match.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build a minimal DBabel resource-loading plan from a validated task context."""
import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "resource_router.yaml"
TASK_SCHEMA = ROOT / "schemas" / "task_context.schema.json"
PLAN_SCHEMA = ROOT / "schemas" / "resource_plan.schema.json"
ROUTER_SCHEMA = ROOT / "schemas" / "resource_router.schema.json"
EXAMPLE_ROUTER = ROOT / "config" / "example_router.yaml"


class RoutingError(ValueError):
    """Raised when routing input or package routing metadata is invalid."""


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _validator(schema_path: Path) -> Draft202012Validator:
    return Draft202012Validator(_load_json(schema_path))


def _format_errors(errors: Iterable) -> List[str]:
    result = []
    for error in sorted(errors, key=lambda e: list(e.absolute_path)):
        location = ".".join(str(x) for x in error.absolute_path) or "<root>"
        result.append("{}: {}".format(location, error.message))
    return result


def validate_task_context(context: dict) -> List[str]:
    return _format_errors(_validator(TASK_SCHEMA).iter_errors(context))


def validate_resource_plan(plan: dict) -> List[str]:
    return _format_errors(_validator(PLAN_SCHEMA).iter_errors(plan))


def load_router_config(path: Path = DEFAULT_CONFIG) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RoutingError("resource router root must be a mapping")
    errors = _format_errors(_validator(ROUTER_SCHEMA).iter_errors(data))
    if errors:
        raise RoutingError("invalid resource router config: " + "; ".join(errors))
    return data


def _append_unique(items: List[str], seen: Set[str], values: Iterable[str]) -> None:
    for value in values:
        if value not in seen:
            items.append(value)
            seen.add(value)


def _all_routable_resources(config: dict) -> List[str]:
    ordered = []
    seen = set()

    for resources in config.get("input_resources", {}).values():
        _append_unique(ordered, seen, resources)

    for resources in config.get("mode_resources", {}).values():
        _append_unique(ordered, seen, resources)

    format_resource = config.get("format_resource", {}).get("reference")
    if format_resource:
        _append_unique(ordered, seen, [format_resource])

    for resources in config.get("signal_resources", {}).values():
        _append_unique(ordered, seen, resources)

    aligned = config.get("aligned_qa", {}).get("resource")
    if aligned:
        _append_unique(ordered, seen, [aligned])

    for resources in config.get("risk_resources", {}).values():
        _append_unique(ordered, seen, resources)

    research = config.get("research", {})
    _append_unique(
        ordered,
        seen,
        [
            x
            for x in (
                research.get("evidence_resource"),
                research.get("search_resource"),
            )
            if x
        ],
    )
    return ordered


def _check_resource_paths(resources: Iterable[str]) -> None:
    missing = [resource for resource in resources if not (ROOT / resource).is_file()]
    if missing:
        raise RoutingError(
            "router references missing package resources: {}".format(", ".join(missing))
        )


def _validate_example_routes(config: dict) -> None:
    if not EXAMPLE_ROUTER.is_file():
        raise RoutingError("missing config/example_router.yaml")
    example_data = yaml.safe_load(EXAMPLE_ROUTER.read_text(encoding="utf-8"))
    route_ids = {
        route.get("id")
        for route in example_data.get("routes", [])
        if isinstance(route, dict)
    }
    configured = set(config.get("example_routes", {}).values())
    unknown = sorted(configured - route_ids)
    if unknown:
        raise RoutingError(
            "resource router references unknown example routes: {}".format(
                ", ".join(unknown)
            )
        )


def build_plan(
    context: dict,
    config: Optional[dict] = None,
    check_package_paths: bool = True,
) -> dict:
    errors = validate_task_context(context)
    if errors:
        raise RoutingError("invalid task context: " + "; ".join(errors))

    config = config or load_router_config()
    all_resources = _all_routable_resources(config)

    if check_package_paths:
        _check_resource_paths(all_resources)
        _validate_example_routes(config)

    mode = context["mode"]
    fmt = context["format"]
    input_kind = context.get("input_kind", "none")
    signals = context["signals"]
    risk_tags = context["risk_tags"]

    load_now: List[str] = []
    seen: Set[str] = set()
    notes: List[str] = []

    input_resources = config.get("input_resources", {}).get(input_kind)
    if input_resources is None:
        raise RoutingError("input kind has no resource-router entry: {}".format(input_kind))
    _append_unique(load_now, seen, input_resources)

    mode_resources = config.get("mode_resources", {}).get(mode)
    if mode_resources is None:
        raise RoutingError("mode has no resource-router entry: {}".format(mode))
    _append_unique(load_now, seen, mode_resources)

    if fmt in set(config.get("structured_formats", [])):
        format_resource = config.get("format_resource", {}).get("reference")
        if format_resource:
            _append_unique(load_now, seen, [format_resource])

    signal_resources = config.get("signal_resources", {})
    for signal_name, resources in signal_resources.items():
        if signals.get(signal_name) is True:
            _append_unique(load_now, seen, resources)

    aligned_qa = config.get("aligned_qa", {})
    if (
        signals["aligned_bilingual_units"]
        and mode in set(aligned_qa.get("modes", []))
    ):
        resource = aligned_qa.get("resource")
        if resource:
            _append_unique(load_now, seen, [resource])
    elif mode in set(aligned_qa.get("modes", [])):
        notes.append(
            "Deterministic bilingual QA was not routed because aligned bilingual units are unavailable."
        )

    for risk in risk_tags:
        _append_unique(
            load_now,
            seen,
            config.get("risk_resources", {}).get(risk, []),
        )

    research = config.get("research", {})
    evidence_resource = research.get("evidence_resource")
    search_resource = research.get("search_resource")
    source_research_mode = research.get("source_research_mode")

    explicit_research = signals["external_research_requested"]
    unresolved_need = signals["needs_external_evidence"]
    approved_resolves = signals["approved_resource_resolves_scope"]
    public_permitted = signals["public_research_permitted"]

    research_needed = (
        mode == source_research_mode
        or explicit_research
        or (unresolved_need and not approved_resolves)
    )

    if research_needed and evidence_resource:
        _append_unique(load_now, seen, [evidence_resource])

    if research_needed and public_permitted and search_resource:
        _append_unique(load_now, seen, [search_resource])
    elif research_needed and not public_permitted:
        notes.append(
            "Public research is not permitted; public search strategy was not routed."
        )

    if unresolved_need and approved_resolves and not explicit_research and mode != source_research_mode:
        notes.append(
            "External research was suppressed because an approved scoped resource already resolves the task."
        )

    if signals["repair_requested"] and not signals["repair_authorized"]:
        notes.append(
            "Repair is requested but not authorized; repair-specific QA/release rules were not routed."
        )

    example_map = config.get("example_routes", {})
    max_examples = int(config.get("policy", {}).get("max_example_sections", 3))
    matching_examples = []
    for risk in risk_tags:
        route_id = example_map.get(risk)
        if route_id and route_id not in matching_examples:
            matching_examples.append(route_id)

    example_sections = matching_examples[:max_examples]
    if len(matching_examples) > max_examples:
        notes.append(
            "Worked-example routing was capped at {} sections; risk tag order is treated as relevance order.".format(
                max_examples
            )
        )

    example_data = yaml.safe_load(EXAMPLE_ROUTER.read_text(encoding="utf-8"))
    case_paths = {route["id"]: route["path"] for route in example_data["routes"]}
    example_files = [case_paths[section] for section in example_sections]
    if check_package_paths:
        _check_resource_paths(example_files)
    _append_unique(load_now, seen, example_files)
    not_loaded = [resource for resource in all_resources if resource not in seen]

    if config.get("policy", {}).get("deny_full_reference_sweep") is True:
        notes.append(
            "Full reference sweep is prohibited; only routed resources should be loaded."
        )

    plan = {
        "format_version": "1.0",
        "mode": mode,
        "load_now": load_now,
        "not_loaded": not_loaded,
        "example_sections": example_sections,
        "example_files": example_files,
        "notes": notes,
    }

    plan_errors = validate_resource_plan(plan)
    if plan_errors:
        raise RoutingError("generated invalid resource plan: " + "; ".join(plan_errors))
    return plan


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("context", type=Path, help="Task context JSON file")
    parser.add_argument("--output", type=Path, help="Write plan JSON to this path")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Resource-router YAML file",
    )
    args = parser.parse_args()

    try:
        context = _load_json(args.context)
        config = load_router_config(args.config)
        plan = build_plan(context, config=config, check_package_paths=True)
    except (OSError, ValueError, json.JSONDecodeError, yaml.YAMLError, RoutingError) as exc:
        parser.exit(2, "Cannot build resource plan: {}\n".format(exc))

    rendered = json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()

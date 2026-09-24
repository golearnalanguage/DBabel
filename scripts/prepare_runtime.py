#!/usr/bin/env python3
"""Prepare a validated DBabel runtime plan with progressive resource loading."""
import argparse
import json
from pathlib import Path
from typing import Iterable, List, Optional

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from preflight_document import PreflightError, preflight_document
from route_resources import RoutingError, build_plan, validate_task_context

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"
SCHEMA_BASE = "https://dbabel.invalid/schemas/"


class RuntimePreparationError(ValueError):
    pass


def _validator(schema_name: str) -> Draft202012Validator:
    schemas = {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in SCHEMA_DIR.glob("*.json")
    }
    registry = Registry().with_resources(
        (SCHEMA_BASE + name, Resource.from_contents(schema))
        for name, schema in schemas.items()
    )
    return Draft202012Validator(
        {"$ref": SCHEMA_BASE + schema_name},
        registry=registry,
    )


def validate_runtime_plan(plan: dict) -> List[str]:
    errors = []
    for error in _validator("runtime_plan.schema.json").iter_errors(plan):
        location = ".".join(str(x) for x in error.absolute_path) or "<root>"
        errors.append("{}: {}".format(location, error.message))
    return sorted(errors)


def _signals(
    *,
    mode: str,
    has_project_glossary: bool = False,
    aligned_bilingual_units: bool = False,
    structured_output: bool = False,
    needs_external_evidence: bool = False,
    external_research_requested: bool = False,
    public_research_permitted: bool = False,
    approved_resource_resolves_scope: bool = False,
    repair_requested: bool = False,
    repair_authorized: bool = False,
) -> dict:
    if mode == "REPAIR":
        repair_requested = True
    if repair_authorized:
        repair_requested = True
    return {
        "has_project_glossary": bool(has_project_glossary),
        "aligned_bilingual_units": bool(aligned_bilingual_units),
        "structured_output": bool(structured_output),
        "needs_external_evidence": bool(needs_external_evidence),
        "external_research_requested": bool(external_research_requested),
        "public_research_permitted": bool(public_research_permitted),
        "approved_resource_resolves_scope": bool(approved_resource_resolves_scope),
        "repair_requested": bool(repair_requested),
        "repair_authorized": bool(repair_authorized),
    }


def prepare_runtime(
    *,
    mode: str,
    file_path: Optional[Path] = None,
    inline_format: str = "none",
    source_language: Optional[str] = None,
    target_language: Optional[str] = None,
    scope: Optional[dict] = None,
    risk_tags: Optional[Iterable[str]] = None,
    declared_backends: Optional[Iterable[str]] = None,
    fallback_backend: str = "auto",
    has_project_glossary: bool = False,
    aligned_bilingual_units: bool = False,
    structured_output: bool = False,
    needs_external_evidence: bool = False,
    external_research_requested: bool = False,
    public_research_permitted: bool = False,
    approved_resource_resolves_scope: bool = False,
    repair_requested: bool = False,
    repair_authorized: bool = False,
) -> dict:
    risk_tags = list(risk_tags or [])
    signals = _signals(
        mode=mode,
        has_project_glossary=has_project_glossary,
        aligned_bilingual_units=aligned_bilingual_units,
        structured_output=structured_output,
        needs_external_evidence=needs_external_evidence,
        external_research_requested=external_research_requested,
        public_research_permitted=public_research_permitted,
        approved_resource_resolves_scope=approved_resource_resolves_scope,
        repair_requested=repair_requested,
        repair_authorized=repair_authorized,
    )

    preflight = None
    selected_backend = None

    if file_path is not None:
        preflight = preflight_document(
            Path(file_path),
            intent="repair" if mode == "REPAIR" else "audit",
            declared_backends=declared_backends,
            fallback_backend=fallback_backend,
        )
        selection = preflight["selection"]
        probe = preflight["probe"]
        blocked_identity = probe["status"] in {"CONFLICT", "UNKNOWN", "EXTENSION_ONLY"}
        task_format = "unknown" if blocked_identity else probe["task_context_format"]
        preflight_status = selection["status"]
        input_kind = "file"
        selected_backend = selection["selected_backend"]

        if selection["status"] == "READY":
            runtime_status = "READY_FOR_INGEST"
            next_step = "LOAD_ROUTED_RESOURCES_THEN_INGEST"
            reason = (
                "File format and an eligible parser backend are preflight-ready; "
                "actual ingest coverage must still be validated."
            )
        else:
            runtime_status = "BLOCKED"
            next_step = "RESOLVE_PREFLIGHT_BLOCKER"
            reason = selection["reason"]
    else:
        if inline_format not in {"none", "txt", "md", "html", "json", "csv", "xml"}:
            raise RuntimePreparationError(
                "inline format is not supported: {}".format(inline_format)
            )
        input_kind = "inline_text"
        task_format = inline_format
        preflight_status = "NOT_REQUIRED"
        runtime_status = "READY_FOR_TASK"
        next_step = "LOAD_ROUTED_RESOURCES"
        reason = "Inline text does not require document parser preflight."

    context = {
        "format_version": "1.0",
        "mode": mode,
        "format": task_format,
        "input_kind": input_kind,
        "preflight_status": preflight_status,
        "signals": signals,
        "risk_tags": risk_tags,
    }
    if source_language:
        context["source_language"] = source_language
    if target_language:
        context["target_language"] = target_language
    if scope:
        context["scope"] = scope

    context_errors = validate_task_context(context)
    if context_errors:
        raise RuntimePreparationError(
            "generated invalid task context: " + "; ".join(context_errors)
        )

    resource_plan = build_plan(context)

    plan = {
        "format_version": "1.0",
        "input_kind": input_kind,
        "preflight": preflight,
        "task_context": context,
        "resource_plan": resource_plan,
        "runtime": {
            "status": runtime_status,
            "selected_backend": selected_backend,
            "next_step": next_step,
            "reason": reason,
        },
    }

    errors = validate_runtime_plan(plan)
    if errors:
        raise RuntimePreparationError(
            "generated invalid runtime plan: " + "; ".join(errors)
        )
    return plan


def _scope_from_args(args: argparse.Namespace) -> Optional[dict]:
    scope = {}
    for key in ("vendor", "product", "version", "domain", "text_role"):
        value = getattr(args, key)
        if value:
            scope[key] = value
    return scope or None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        required=True,
        choices=[
            "LOOKUP", "AUDIT", "BILINGUAL_REVIEW", "TRANSLATE",
            "REPAIR", "SOURCE_RESEARCH", "CLAIM_ROUTE", "GOVERNANCE",
        ],
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--file", type=Path)
    source.add_argument(
        "--inline-format",
        choices=["none", "txt", "md", "html", "json", "csv", "xml"],
        default="none",
    )
    parser.add_argument("--source-language")
    parser.add_argument("--target-language")
    parser.add_argument("--vendor")
    parser.add_argument("--product")
    parser.add_argument("--version")
    parser.add_argument("--domain")
    parser.add_argument("--text-role")
    parser.add_argument("--risk", action="append", default=[])
    parser.add_argument("--declare-backend", action="append", default=[])
    parser.add_argument(
        "--fallback-backend",
        choices=["auto", "none", "filetype", "python_magic"],
        default="auto",
    )

    for name in (
        "has-project-glossary",
        "aligned-bilingual-units",
        "structured-output",
        "needs-external-evidence",
        "external-research-requested",
        "public-research-permitted",
        "approved-resource-resolves-scope",
        "repair-requested",
        "repair-authorized",
    ):
        parser.add_argument("--" + name, action="store_true")

    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        plan = prepare_runtime(
            mode=args.mode,
            file_path=args.file,
            inline_format=args.inline_format,
            source_language=args.source_language,
            target_language=args.target_language,
            scope=_scope_from_args(args),
            risk_tags=args.risk,
            declared_backends=args.declare_backend,
            fallback_backend=args.fallback_backend,
            has_project_glossary=args.has_project_glossary,
            aligned_bilingual_units=args.aligned_bilingual_units,
            structured_output=args.structured_output,
            needs_external_evidence=args.needs_external_evidence,
            external_research_requested=args.external_research_requested,
            public_research_permitted=args.public_research_permitted,
            approved_resource_resolves_scope=args.approved_resource_resolves_scope,
            repair_requested=args.repair_requested,
            repair_authorized=args.repair_authorized,
        )
    except (OSError, ValueError, RuntimePreparationError, RoutingError, PreflightError) as exc:
        parser.exit(2, "Runtime preparation failed: {}\n".format(exc))

    rendered = json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")

    if plan["runtime"]["status"] == "BLOCKED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

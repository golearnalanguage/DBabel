#!/usr/bin/env python3
"""Check DBabel package metadata, schemas, cross-contracts, links, and checksums."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess

import yaml
from jsonschema import Draft202012Validator
from validate_report import ROOT, validate_report
from suggest_translation_techniques import (
    candidate_report_cross_errors,
    validate_candidate_report_schema,
)
from technique_contract import load_translation_registry
from extract_translation_signals import (
    surface_rule_cross_errors,
)
from version_info import PACKAGE_VERSION, REVIEW_WORKBENCH_VERSION

LEGACY_REPORT_VERSIONS = {'1.3.0', '1.4.0'}
SUPPORTED_REPORT_VERSIONS = LEGACY_REPORT_VERSIONS | {PACKAGE_VERSION}

GLOSSARY_CSV_HEADER = [
    'entry_id', 'source_language', 'source_term', 'behavior', 'approval',
    'target_language', 'preferred_target', 'admitted_targets', 'forbidden_targets',
    'vendor', 'product', 'version', 'domain', 'text_roles', 'match_mode',
    'case_sensitive', 'notes',
]

REQUIRED_WORKFLOW_STATES = {
    'INTAKE', 'TASK_CONTEXT', 'FORMAT_PROBE', 'CAPABILITY_PROBE',
    'RESOURCE_ROUTING', 'INGEST', 'INGEST_VALIDATION', 'STRUCTURE', 'CONTEXT',
    'EXTRACTION', 'CLASSIFICATION', 'USER_RESOURCE_RESOLUTION',
    'SOURCE_RESEARCH', 'EVIDENCE_ASSESSMENT', 'ADJUDICATION', 'TRANSLATION',
    'DETERMINISTIC_QA', 'QA', 'REPAIR', 'ROUND_TRIP_QA',
    'PROJECT_GLOSSARY_CANDIDATE', 'OUTPUT',
}

WORKFLOW_SAFETY_RULES = {
    'full_reference_sweep_allowed': False,
    'file_extension_is_format_proof': False,
    'preflight_ready_is_ingest_success': False,
    'deterministic_qa_is_semantic_verdict': False,
    'deterministic_qa_authorizes_repair': False,
    'global_auto_approval_of_discovered_terms': False,
}

DETERMINISTIC_QA_SAFETY_POLICY = {
    'deterministic_output_authorizes_repair': False,
    'fail_closed_on_missing_scope': True,
    'apply_only_project_approved_glossary_entries': True,
}


def package_paths(root=ROOT):
    """Return package files, respecting Git ignore rules in a checkout."""
    if (root / '.git').exists():
        names = subprocess.check_output(
            ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
            cwd=root).decode().split('\0')
        return sorted({name for name in names if name and name != 'MANIFEST.sha256'
                       and (root / name).is_file()})
    ignored = {'.git', '.venv', '__pycache__', '.pytest_cache', 'output', 'cache',
               'source_cache', 'private', 'customer_data', 'project_glossary_private',
               'translation_memory_private'}
    return sorted(p.relative_to(root).as_posix() for p in root.rglob('*')
                  if p.is_file() and not (set(p.relative_to(root).parts) & ignored)
                  and p.name not in {'MANIFEST.sha256', '.DS_Store'}
                  and not p.name.startswith('.env'))


def manifest(paths, root=ROOT):
    return ''.join(f'{hashlib.sha256((root / name).read_bytes()).hexdigest()}  ./{name}\n'
                   for name in paths)


def _read_yaml(path):
    return yaml.safe_load(path.read_text(encoding='utf-8'))


def _read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def _schema_refs(value):
    if isinstance(value, dict):
        if '$ref' in value and not value['$ref'].startswith('#'):
            yield value['$ref']
        for item in value.values():
            yield from _schema_refs(item)
    elif isinstance(value, list):
        for item in value:
            yield from _schema_refs(item)


def _routed_paths(value):
    """Yield repository-relative resource paths from nested router data."""
    prefixes = ('references/', 'config/', 'schemas/', 'templates/', 'examples/',
                'docs/', 'scripts/', 'plugins/')
    if isinstance(value, dict):
        for item in value.values():
            yield from _routed_paths(item)
    elif isinstance(value, list):
        for item in value:
            yield from _routed_paths(item)
    elif isinstance(value, str):
        if value == 'SKILL.md' or value.startswith(prefixes):
            yield value


def _example_heading_ids(text):
    return re.findall(r'^###\s+([A-E][1-9][0-9]*)\b', text, re.M)


def _frontmatter(skill_text):
    match = re.match(r'^---\n(.*?)\n---\n', skill_text, re.S)
    if not match:
        return None
    return yaml.safe_load(match.group(1))


def cross_contract_errors(root=ROOT):
    """Validate consistency between DBabel's independently stored contracts."""
    errors = []

    # Public version surfaces.
    readme = (root / 'README.md').read_text(encoding='utf-8')
    match = re.search(r'Repository version:\s*\*\*([0-9]+\.[0-9]+\.[0-9]+)\*\*', readme)
    if not match or match.group(1) != PACKAGE_VERSION:
        errors.append('README.md: repository version does not match package version')

    readme_zh = (root / 'README.zh-CN.md').read_text(encoding='utf-8')
    match_zh = re.search(r'当前仓库包版本(?:为|：)?\s*\*\*([0-9]+\.[0-9]+\.[0-9]+)\*\*', readme_zh)
    if not match_zh or match_zh.group(1) != PACKAGE_VERSION:
        errors.append('README.zh-CN.md: repository version does not match package version')

    workbench_match = re.search(
        r'Review Workbench version:\s*\*\*([^*]+)\*\*',
        readme,
    )
    if (
        not workbench_match
        or workbench_match.group(1) != REVIEW_WORKBENCH_VERSION
    ):
        errors.append(
            'README.md: Review Workbench version drifted'
        )

    workbench_match_zh = re.search(
        r'Review Workbench 当前版本为\s*\*\*([^*]+)\*\*',
        readme_zh,
    )
    if (
        not workbench_match_zh
        or workbench_match_zh.group(1) != REVIEW_WORKBENCH_VERSION
    ):
        errors.append(
            'README.zh-CN.md: Review Workbench version drifted'
        )

    workbench_doc = (
        root / 'docs/REVIEW_WORKBENCH.md'
    ).read_text(encoding='utf-8')

    if (
        '**{}**'.format(REVIEW_WORKBENCH_VERSION)
        not in workbench_doc
    ):
        errors.append(
            'docs/REVIEW_WORKBENCH.md: Workbench version drifted'
        )

    changelog = (root / 'CHANGELOG.md').read_text(encoding='utf-8')
    unreleased = f'## Unreleased — {PACKAGE_VERSION}' in changelog
    released = re.search(rf'^##\s+{re.escape(PACKAGE_VERSION)}\s+—\s+\d{{4}}-\d{{2}}-\d{{2}}$',
                         changelog, re.M) is not None
    if not (unreleased or released):
        errors.append('CHANGELOG.md: current package version is not represented')

    # Report producer/validator compatibility.
    audit_schema = _read_json(root / 'schemas/audit_report.schema.json')
    version_rule = audit_schema.get('properties', {}).get('dbabel_version', {})
    allowed_report_versions = set(version_rule.get('enum', []))
    if allowed_report_versions != SUPPORTED_REPORT_VERSIONS:
        errors.append('schemas/audit_report.schema.json: supported report versions drifted')

    example_report = _read_json(root / 'examples/audit_report.json')
    if example_report.get('dbabel_version') != PACKAGE_VERSION:
        errors.append('examples/audit_report.json: producer version does not match package version')

    # Example router must cover exactly the published worked-example sections.
    example_router = _read_yaml(root / 'config/example_router.yaml')
    route_ids = [item.get('id') for item in example_router.get('routes', [])
                 if isinstance(item, dict)]
    heading_ids = _example_heading_ids(
        (root / 'examples/technical_translation_review_examples.zh-CN.md')
        .read_text(encoding='utf-8'))
    if len(route_ids) != len(set(route_ids)):
        errors.append('config/example_router.yaml: duplicate route id')
    if len(heading_ids) != len(set(heading_ids)):
        errors.append('technical translation examples: duplicate section id')
    if set(route_ids) != set(heading_ids):
        errors.append('config/example_router.yaml: route IDs do not match worked-example sections')

    # Resource router paths and example-route IDs must resolve.
    resource_router = _read_yaml(root / 'config/resource_router.yaml')
    for rel in sorted(set(_routed_paths(resource_router))):
        if not (root / rel).is_file():
            errors.append(f'config/resource_router.yaml: routed resource does not exist: {rel}')
    routed_example_ids = set((resource_router.get('example_routes') or {}).values())
    if routed_example_ids != set(route_ids):
        errors.append('config/resource_router.yaml: example routes drifted from example_router.yaml')

    policy = resource_router.get('policy', {})
    if policy.get('progressive_loading') is not True:
        errors.append('config/resource_router.yaml: progressive_loading must remain true')
    if policy.get('deny_full_reference_sweep') is not True:
        errors.append('config/resource_router.yaml: deny_full_reference_sweep must remain true')
    if policy.get('load_only_routed_resources') is not True:
        errors.append('config/resource_router.yaml: load_only_routed_resources must remain true')
    if policy.get('examples_are_evidence') is not False:
        errors.append('config/resource_router.yaml: examples_are_evidence must remain false')

    # Glossary CSV template must remain compatible with the loader contract.
    with (root / 'templates/project_glossary.csv').open(
            'r', encoding='utf-8', newline='') as handle:
        header = next(csv.reader(handle), [])
    if header != GLOSSARY_CSV_HEADER:
        errors.append('templates/project_glossary.csv: header drifted from glossary loader contract')

    # Format registry references must resolve internally.
    format_registry = _read_yaml(root / 'config/format_registry.yaml')
    formats = format_registry.get('formats', {})
    backends = format_registry.get('backends', {})
    for extension, fmt in (format_registry.get('extensions') or {}).items():
        if fmt not in formats:
            errors.append(f'config/format_registry.yaml: extension {extension} references unknown format {fmt}')
    for fmt_name, spec in formats.items():
        for key in ('audit_backends', 'repair_backends'):
            for backend in spec.get(key, []):
                if backend not in backends:
                    errors.append(
                        f'config/format_registry.yaml: {fmt_name}.{key} references unknown backend {backend}')
    registry_context_formats = {spec.get('task_context_format') for spec in formats.values()
                                if isinstance(spec, dict) and spec.get('task_context_format')}
    structured_formats = set(resource_router.get('structured_formats', []))
    unknown_structured = structured_formats - registry_context_formats
    if unknown_structured:
        errors.append('config/resource_router.yaml: structured formats missing from format registry: '
                      + ', '.join(sorted(unknown_structured)))

    adapter_paths = {
        'filetype': 'plugins/format_backends/filetype_backend.py',
        'python_magic': 'plugins/format_backends/python_magic_backend.py',
    }
    for backend, rel in adapter_paths.items():
        if backend in backends and not (root / rel).is_file():
            errors.append(f'config/format_registry.yaml: registered backend {backend} is missing adapter {rel}')

    # Task Context is the shared vocabulary between preflight, registry, and router.
    task_context_schema = _read_json(root / 'schemas/task_context.schema.json')
    context_properties = task_context_schema.get('properties', {})
    known_modes = set(context_properties.get('mode', {}).get('enum', []))
    known_formats = set(context_properties.get('format', {}).get('enum', []))
    known_risks = set(context_properties.get('risk_tags', {}).get('items', {}).get('enum', []))
    unknown_registry_formats = registry_context_formats - known_formats
    if unknown_registry_formats:
        errors.append('config/format_registry.yaml: task_context_format missing from Task Context schema: '
                      + ', '.join(sorted(unknown_registry_formats)))
    unknown_router_formats = structured_formats - known_formats
    if unknown_router_formats:
        errors.append('config/resource_router.yaml: structured format missing from Task Context schema: '
                      + ', '.join(sorted(unknown_router_formats)))
    routed_modes = set((resource_router.get('mode_resources') or {}))
    routed_modes.update(resource_router.get('aligned_qa', {}).get('modes', []))
    unknown_modes = routed_modes - known_modes
    if unknown_modes:
        errors.append('config/resource_router.yaml: routed mode missing from Task Context schema: '
                      + ', '.join(sorted(unknown_modes)))
    routed_risks = set((resource_router.get('risk_resources') or {}))
    routed_risks.update((resource_router.get('example_routes') or {}))
    unknown_risks = routed_risks - known_risks
    if unknown_risks:
        errors.append('config/resource_router.yaml: risk tag missing from Task Context schema: '
                      + ', '.join(sorted(unknown_risks)))

    # Workflow safety and known state contract.
    workflow = _read_yaml(root / 'config/workflow.yaml')
    states = workflow.get('states', [])
    if len(states) != len(set(states)):
        errors.append('config/workflow.yaml: duplicate workflow state')
    missing_states = REQUIRED_WORKFLOW_STATES - set(states)
    if missing_states:
        errors.append('config/workflow.yaml: missing required states: '
                      + ', '.join(sorted(missing_states)))
    unknown_conditions = set((workflow.get('conditions') or {})) - set(states)
    if unknown_conditions:
        errors.append('config/workflow.yaml: condition keys are not workflow states: '
                      + ', '.join(sorted(unknown_conditions)))
    workflow_rules = workflow.get('rules', {})
    for key, expected in WORKFLOW_SAFETY_RULES.items():
        if workflow_rules.get(key) != expected:
            errors.append(f'config/workflow.yaml: safety invariant {key} must be {expected}')

    # Accuracy Core safety policy is part of the package boundary.
    deterministic_qa = _read_yaml(root / 'config/deterministic_qa.yaml')
    qa_policy = deterministic_qa.get('policy', {})
    for key, expected in DETERMINISTIC_QA_SAFETY_POLICY.items():
        if qa_policy.get(key) != expected:
            errors.append(f'config/deterministic_qa.yaml: safety invariant {key} must be {expected}')


    # Technical translation technique registry is a routed package contract.
    translation_registry = _read_yaml(
        root / 'config/translation_techniques.yaml'
    )
    translation_schema = _read_json(
        root / 'schemas/translation_techniques.schema.json'
    )

    translation_validation_errors = sorted(
        Draft202012Validator(
            translation_schema
        ).iter_errors(
            translation_registry
        ),
        key=lambda error: list(error.absolute_path),
    )

    for error in translation_validation_errors:
        location = '.'.join(
            str(value)
            for value in error.absolute_path
        ) or '<root>'

        errors.append(
            'config/translation_techniques.yaml: {}: {}'.format(
                location,
                error.message,
            )
        )

    techniques = translation_registry.get('techniques', [])
    technique_ids = [
        item.get('id')
        for item in techniques
        if isinstance(item, dict)
    ]

    if len(technique_ids) != len(set(technique_ids)):
        errors.append(
            'config/translation_techniques.yaml: duplicate technique id'
        )

    technique_id_set = set(technique_ids)

    playbook_text = (
        root / 'references/18_TECHNICAL_TRANSLATION_PLAYBOOK.md'
    ).read_text(encoding='utf-8')

    playbook_ids = re.findall(
        r'^###\s+\d+\.\s+`([A-Z][A-Z0-9_]+)`\s*$',
        playbook_text,
        re.M,
    )

    if len(playbook_ids) != len(set(playbook_ids)):
        errors.append(
            'references/18_TECHNICAL_TRANSLATION_PLAYBOOK.md: duplicate technique id'
        )

    if set(playbook_ids) != technique_id_set:
        errors.append(
            'translation technique IDs drifted between playbook and registry'
        )

    transformations = translation_registry.get(
        'transformations',
        [],
    )
    transformation_ids = [
        item.get('id')
        for item in transformations
        if isinstance(item, dict)
    ]

    if len(transformation_ids) != len(set(transformation_ids)):
        errors.append(
            'config/translation_techniques.yaml: duplicate transformation id'
        )

    known_transformations = set(transformation_ids)
    referenced_transformations = set()

    for item in techniques:
        if not isinstance(item, dict):
            continue

        allowed = set(
            item.get('allowed_transformations', [])
        )
        restricted = set(
            item.get('restricted_transformations', [])
        )

        overlap = allowed & restricted

        if overlap:
            errors.append(
                'config/translation_techniques.yaml: {} has transformations both allowed and restricted: {}'.format(
                    item.get('id', '<unknown>'),
                    ', '.join(sorted(overlap)),
                )
            )

        referenced_transformations.update(allowed)
        referenced_transformations.update(restricted)

    unknown_transformations = (
        referenced_transformations
        - known_transformations
    )

    if unknown_transformations:
        errors.append(
            'config/translation_techniques.yaml: unknown transformations: '
            + ', '.join(sorted(unknown_transformations))
        )

    known_qa_checks = set(
        (deterministic_qa.get('checks') or {})
    )
    referenced_qa_checks = set()

    for item in techniques:
        if not isinstance(item, dict):
            continue

        qa_mapping = item.get('qa_mapping') or {}
        referenced_qa_checks.update(
            qa_mapping.get(
                'deterministic_checks',
                [],
            )
        )

    unknown_qa_checks = (
        referenced_qa_checks
        - known_qa_checks
    )

    if unknown_qa_checks:
        errors.append(
            'config/translation_techniques.yaml: unknown deterministic QA checks: '
            + ', '.join(sorted(unknown_qa_checks))
        )

    surface_rules = _read_yaml(
        root / 'config/surface_signal_rules.yaml'
    )

    surface_schema = _read_json(
        root / 'schemas/surface_signal_rules.schema.json'
    )

    surface_validation_errors = sorted(
        Draft202012Validator(
            surface_schema
        ).iter_errors(
            surface_rules
        ),
        key=lambda error: list(
            error.absolute_path
        ),
    )

    for error in surface_validation_errors:
        location = '.'.join(
            str(value)
            for value
            in error.absolute_path
        ) or '<root>'

        errors.append(
            'config/surface_signal_rules.yaml: {}: {}'.format(
                location,
                error.message,
            )
        )

    if not surface_validation_errors:
        errors.extend(
            'config/surface_signal_rules.yaml: {}'.format(
                error
            )
            for error in surface_rule_cross_errors(
                surface_rules,
                translation_registry,
            )
        )

    translation_resources = {
        'references/18_TECHNICAL_TRANSLATION_PLAYBOOK.md',
        'config/translation_techniques.yaml',
    }

    for mode in (
        'BILINGUAL_REVIEW',
        'TRANSLATE',
    ):
        routed = set(
            (resource_router.get('mode_resources') or {}).get(
                mode,
                [],
            )
        )

        missing = translation_resources - routed

        if missing:
            errors.append(
                'config/resource_router.yaml: {} missing translation resources: {}'.format(
                    mode,
                    ', '.join(sorted(missing)),
                )
            )

    repair_routed = set(
        (resource_router.get('mode_resources') or {}).get(
            'REPAIR',
            [],
        )
    )

    unexpected_repair_resources = (
        translation_resources
        & repair_routed
    )

    if unexpected_repair_resources:
        errors.append(
            'config/resource_router.yaml: REPAIR must not default-route translation technique resources: '
            + ', '.join(sorted(unexpected_repair_resources))
        )


    return errors


def example_report_errors(root=ROOT):
    """Validate report-like examples through their registered contracts."""

    errors = []

    for path in sorted(
        (root / 'examples').glob('*report.json')
    ):
        value = _read_json(path)

        if path.name == 'audit_report.json':
            errors.extend(
                '{}: {}'.format(
                    path.name,
                    error,
                )
                for error in validate_report(
                    value
                )
            )
            continue

        if path.name == 'technique_candidate_report.json':
            schema_errors = (
                validate_candidate_report_schema(
                    value
                )
            )

            errors.extend(
                '{}: schema {}'.format(
                    path.name,
                    error,
                )
                for error in schema_errors
            )

            if not schema_errors:
                technique_registry = (
                    load_translation_registry(
                        root
                    )
                )

                errors.extend(
                    '{}: {}'.format(
                        path.name,
                        error,
                    )
                    for error in candidate_report_cross_errors(
                        value,
                        technique_registry,
                    )
                )

            continue

        errors.append(
            '{}: report-like example has no registered validator'.format(
                path.name
            )
        )

    return errors


def check_package(write_manifest=False):
    errors = []
    paths = package_paths()
    skill = (ROOT / 'SKILL.md').read_text(encoding='utf-8')
    metadata = _frontmatter(skill)
    if metadata is None:
        return ['SKILL.md: missing YAML frontmatter']
    allowed = {'name', 'description', 'license', 'compatibility', 'metadata', 'allowed-tools'}
    if not isinstance(metadata, dict):
        return ['SKILL.md: frontmatter must be an object']
    if set(metadata) - allowed:
        errors.append('SKILL.md: unsupported frontmatter field')
    name = metadata.get('name', '')
    if not isinstance(name, str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', name) or len(name) > 64:
        errors.append('SKILL.md: invalid skill name')
    desc = metadata.get('description', '')
    if not isinstance(desc, str) or not 1 <= len(desc) <= 1024:
        errors.append('SKILL.md: invalid description')
    package_meta = metadata.get('metadata', {})
    if not isinstance(package_meta, dict):
        errors.append('SKILL.md: metadata must be an object')
        version = None
    else:
        version = package_meta.get('version')
    if version != PACKAGE_VERSION:
        errors.append('SKILL.md: unexpected package version')

    for path_name in paths:
        path = ROOT / path_name
        try:
            if path.suffix in {'.yaml', '.yml'}:
                data = _read_yaml(path)
                if path_name.startswith('config/'):
                    if not isinstance(data, dict):
                        errors.append(f'{path_name}: config must be an object')
                    elif data.get('version') != version:
                        errors.append(f'{path_name}: inconsistent version')
            if path_name.startswith('schemas/') and path.suffix == '.json':
                schema = _read_json(path)
                Draft202012Validator.check_schema(schema)
                for ref in _schema_refs(schema):
                    local_ref = ref.split(
                        '#',
                        1,
                    )[0]

                    if (
                        local_ref
                        and not (
                            path.parent
                            / local_ref
                        ).is_file()
                    ):
                        errors.append(
                            f'{path_name}: unresolved schema reference {ref}'
                        )
            if path.suffix == '.md':
                text = path.read_text(encoding='utf-8')
                for link in re.findall(r'\[[^\]\n]*\]\(([^)\s]+)\)', text):
                    if re.match(r'^[a-zA-Z]+:|^#', link):
                        continue
                    target = link.split('#')[0]
                    if target and not (path.parent / target).exists():
                        errors.append(f'{path_name}: broken local link {link}')
        except (ValueError, yaml.YAMLError) as exc:
            errors.append(f'{path_name}: {exc}')

    errors.extend(
        example_report_errors(
            ROOT
        )
    )

    try:
        errors.extend(cross_contract_errors(ROOT))
    except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as exc:
        errors.append(f'cross-contract validation failed: {exc}')

    wanted = manifest(paths)
    target = ROOT / 'MANIFEST.sha256'
    if write_manifest and not errors:
        with target.open('w', encoding='utf-8', newline='\n') as handle:
            handle.write(wanted)
    if not target.exists() or target.read_text(encoding='utf-8') != wanted:
        errors.append('MANIFEST.sha256: stale or incomplete; regenerate after intentional edits')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-manifest', action='store_true')
    args = parser.parse_args()
    errors = check_package(args.write_manifest)
    if errors:
        parser.exit(1, '\n'.join(errors) + '\n')
    print('Package checks passed.')


if __name__ == '__main__':
    main()

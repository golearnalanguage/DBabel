#!/usr/bin/env python3
"""Validate DBabel report structure and evidence/repair consistency, offline."""
import argparse
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from technique_contract import (
    load_translation_registry,
    validate_technique_annotation,
)

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://dbabel.invalid/schemas/'


def validator(schema_name='audit_report.schema.json'):
    schemas = {p.name: json.loads(p.read_text(encoding='utf-8'))
               for p in (ROOT / 'schemas').glob('*.json')}
    registry = Registry().with_resources(
        (BASE + name, Resource.from_contents(schema))
        for name, schema in schemas.items())
    return Draft202012Validator(
        {'$ref': BASE + schema_name}, registry=registry,
        format_checker=FormatChecker())


def adequate(source, direct=False):
    matches = {'HIGH'} if direct else {'HIGH', 'MEDIUM'}
    versions = {'EXACT', 'NOT_APPLICABLE'} if direct else {'EXACT', 'NOT_APPLICABLE', 'ADJACENT'}
    discovery_only = {'community_blog_forum_social', 'search_snippet', 'mt_llm_output'}
    return (source['source_type'] not in discovery_only
            and source['source_opened'] and source['evidence_state'] == 'CURRENT'
            and source['authority_match'] in matches
            and source['context_match'] in matches
            and source['version_match'] in versions)


def validate_report(report):
    errors = [f"schema {'.'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
              for e in validator().iter_errors(report)]
    if errors:
        return errors
    technique_registry = (
        load_translation_registry(
            ROOT
        )
    )

    sources = {
        s['id']: s
        for s in report['sources']
    }

    findings = {
        f['id']: f
        for f in report['findings']
    }
    if len(sources) != len(report['sources']):
        errors.append('duplicate source IDs')
    if len(findings) != len(report['findings']):
        errors.append('duplicate finding IDs')
    for f in report['findings']:
        for technique_error in (
            validate_technique_annotation(
                f.get(
                    "technique"
                ),
                technique_registry,
            )
        ):
            errors.append(
                "{}: {}".format(
                    f["id"],
                    technique_error,
                )
            )

        refs = f['evidence_refs']
        if any(ref not in sources for ref in refs):
            errors.append(f"{f['id']}: dangling evidence reference")
        evidence = [sources[ref] for ref in refs if ref in sources]
        needs_evidence = f['decision'] == 'REPLACE' or (
            f['decision'] == 'KEEP' and f['verification_required'])
        if needs_evidence:
            if not any(adequate(s, f['confidence'] == 'HIGH') for s in evidence):
                errors.append(f"{f['id']}: decision lacks adequate opened evidence")
            if f.get('conflicts') or any(s['evidence_state'] == 'CONFLICTING' for s in evidence):
                errors.append(f"{f['id']}: unresolved conflict requires REVIEW")
        if f['decision'] == 'REPLACE' and f['recommendation'] == f['original']:
            errors.append(f"{f['id']}: replacement is unchanged")
    for c in report.get('glossary_candidates', []):
        if any(ref not in sources for ref in c.get('evidence_refs', [])):
            errors.append('glossary candidate: dangling evidence reference')
    for name, qa in [('qa', report['qa']), ('round_trip_qa', report['repair']['round_trip_qa'])]:
        states = [c['status'] for c in qa['checks']]
        if 'FAIL' in states and qa['status'] != 'FAIL':
            errors.append(f'{name}: failed check must produce FAIL')
        if qa['status'] == 'NOT_RUN' and any(s in {'PASS', 'FAIL'} for s in states):
            errors.append(f'{name}: NOT_RUN contradicts performed checks')
        if qa['status'] == 'PASS' and ('NOT_RUN' in states or 'PASS' not in states):
            errors.append(f'{name}: PASS requires performed, passing checks')
    coverage = report['coverage']
    if coverage['status'] == 'FULL' and (coverage['uninspected'] or not coverage['inspected']):
        errors.append('FULL coverage requires inspected scope and no gaps')
    if coverage['status'] != 'FULL' and not coverage['uninspected']:
        errors.append('incomplete coverage requires explicit gaps')
    repair = report['repair']
    modes = {report['mode'], *report.get('secondary_modes', [])}
    if 'REPAIR' in modes and repair['status'] == 'NOT_REQUESTED':
        errors.append('REPAIR mode cannot report NOT_REQUESTED')
    applied = [c for c in repair['changes'] if c['status'] == 'APPLIED']
    seen = set()
    for change in repair['changes']:
        fid = change['finding_id']
        if fid in seen:
            errors.append(f'{fid}: duplicate repair change')
        seen.add(fid)
        f = findings.get(fid)
        if not f:
            errors.append(f'{fid}: repair references missing finding')
            continue
        if change['status'] != 'APPLIED':
            continue
        if not repair['authorized']:
            errors.append(f'{fid}: repair is not authorized')
        if (f['decision'] != 'REPLACE' or f['confidence'] != 'HIGH'
                or f.get('conflicts') or not any(
                    adequate(sources[ref], True) for ref in f['evidence_refs'] if ref in sources)):
            errors.append(f'{fid}: finding is not eligible for repair')
        if (change['location'] != f['location'] or change['before'] != f['original']
                or change['after'] != f.get('recommendation')):
            errors.append(f'{fid}: change does not match the finding')
        if f['protected'] and not change.get('literal_change_authorized', False):
            errors.append(f'{fid}: protected literal change is not authorized')
    if repair['status'] in {'NOT_REQUESTED', 'PROPOSED', 'BLOCKED'} and applied:
        errors.append('repair status contradicts applied changes')
    if repair['status'] in {'APPLIED', 'VERIFIED'}:
        if not repair['authorized'] or not applied or not repair.get('output_document'):
            errors.append('applied repair requires authorization, changes, and output')
    if repair['status'] == 'VERIFIED':
        if repair['round_trip_qa']['status'] != 'PASS':
            errors.append('VERIFIED repair requires passed round-trip QA')
        if any(c['status'] == 'FAILED' for c in repair['changes']):
            errors.append('VERIFIED repair contains failed changes')
    if (report['qa']['status'] == 'FAIL' or repair['status'] == 'FAILED'
            or repair['round_trip_qa']['status'] == 'FAIL') and report['status'] != 'FAILED':
        errors.append('failed QA/repair requires FAILED task status')
    unresolved = any(f['decision'] in {'REVIEW', 'OUT_OF_SCOPE_CLAIM'}
                     for f in report['findings'])
    if report['status'] == 'COMPLETED':
        if coverage['status'] != 'FULL' or report['qa']['status'] != 'PASS' or unresolved:
            errors.append('COMPLETED requires full coverage, passed QA, and resolved findings')
        if repair['status'] not in {'NOT_REQUESTED', 'VERIFIED'}:
            errors.append('COMPLETED cannot contain unfinished repair')
    if report['status'] != 'COMPLETED' and (not report['limitations'] or not report.get('next_actions')):
        errors.append('incomplete/review result requires limitations and next actions')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    try:
        errors = validate_report(json.loads(args.report.read_text(encoding='utf-8')))
    except (OSError, ValueError) as exc:
        parser.exit(1, f'Cannot read report: {exc}\n')
    if errors:
        parser.exit(1, '\n'.join(errors) + '\n')
    print('Report contract valid (source truth and file integrity require agent QA).')


if __name__ == '__main__':
    main()

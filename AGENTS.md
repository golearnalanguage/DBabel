# DBabel Agent Entry Point

This repository contains the DBabel database terminology audit and localization
methodology.

## Runtime entry

Read `SKILL.md` first. It is the normative runtime kernel.

Do **not** read every file under `references/` as a precaution. Build or infer the
task context, perform file preflight when a file is involved, then use
`config/resource_router.yaml` / `scripts/route_resources.py` to load only the
resources required by the current state.

For a reproducible file-task preflight and initial resource plan, use:

```bash
python scripts/prepare_runtime.py --mode AUDIT --file <path> --declare-backend native_agent
```

The runtime plan does not prove successful ingestion. After parsing, validate actual
coverage with `schemas/ingest_report.schema.json` /
`scripts/validate_ingest.py` when machine-readable coverage is used.

Do not treat this repository as a terminology database.

## Required behavior

Before a material terminology decision:

1. resolve the narrowest reliable context;
2. classify the candidate;
3. protect technical tokens;
4. apply user-approved resources only within scope;
5. research only when required/permitted;
6. open the original source before using external evidence;
7. preserve uncertainty when evidence is insufficient.

A deterministic QA finding is only a potential issue. It is not evidence, a
semantic verdict, or repair authorization.

The decision vocabulary is `KEEP`, `REPLACE`, `PROTECT`, `REVIEW`, and
`OUT_OF_SCOPE_CLAIM`.

## Review Workbench handoff

For `BILINGUAL_REVIEW`, `TRANSLATE`, or `REPAIR`, use the Review Workbench when
proposed target changes require human approval or when reviewed content is intended
for native-format export.

The Agent may prepare review units, findings, deterministic issues, evidence, and
suggestions. It must not fabricate human acceptance, keep, edit, defer, block, or
waiver decisions.

Create sessions with `scripts/create_review_session.py`. For native DOCX export,
start `scripts/start_review_workbench.py` with both `--original` and `--output`.
Review-only and Portable Review are allowed, but must not be represented as native
export sessions.

Portable decisions must be imported into the matching `.dbreview` session and
rechecked before export.

## Repository maintenance

For changes to the Skill, schemas, routing, format preflight, or validation tools:

```bash
python -m py_compile scripts/*.py
python -m unittest discover -s tests -v
python scripts/check_package.py
```

After intentional package edits, regenerate `MANIFEST.sha256`:

```bash
python scripts/check_package.py --write-manifest
python scripts/check_package.py
```

Then rerun the full test suite and `git diff --check`. If repository instructions
conflict, `SKILL.md` is authoritative for DBabel workflow behavior.

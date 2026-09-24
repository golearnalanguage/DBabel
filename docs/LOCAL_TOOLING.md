# Local tooling

DBabel's local scripts provide reproducible contracts around routing, format
preflight, glossary handling, deterministic QA, ingest coverage, and structured
reports. They support the Agent workflow; they do not replace source reading or
semantic judgment.

## Baseline environment

Core validation targets Python 3.9+ and uses only the dependencies in
`requirements-dev.txt`. Optional document parsers are not required for package
validation and are not installed automatically.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
```

## Build a runtime plan

For an inline/text-only task:

```bash
python scripts/prepare_runtime.py --mode LOOKUP
```

For a file task:

```bash
python scripts/prepare_runtime.py \
  --mode AUDIT \
  --file ./manual.docx \
  --declare-backend native_agent \
  --output runtime-plan.json
```

The plan combines format preflight, declared/available capabilities, Task Context,
and the initial progressive resource plan. `READY_FOR_INGEST` means a parser may be
used; it does not mean ingest already succeeded.

## Inspect format and capabilities separately

```bash
python scripts/detect_document_format.py ./manual.docx
python scripts/probe_capabilities.py --declare native_agent
python scripts/preflight_document.py \
  ./manual.docx \
  --intent audit \
  --declare-backend native_agent
```

Extension/content conflicts and unverified formats block automatic parser selection.
The built-in detector is bounded and non-executing.

## Validate project terminology

JSON and CSV use the same canonical entry model:

```bash
python scripts/validate_glossary.py project_glossary.json
python scripts/validate_glossary.py project_glossary.csv
```

Only `PROJECT_APPROVED` entries are eligible for deterministic enforcement, and
scope/language requirements fail closed when material context is missing.

## Run deterministic bilingual QA

Input units must already be aligned according to
`schemas/bilingual_unit.schema.json`.

```bash
python scripts/check_bilingual_integrity.py \
  bilingual_units.jsonl \
  --glossary project_glossary.csv \
  --output qa_report.json
```

The report follows `schemas/deterministic_qa_report.schema.json`. Its issues are
`POTENTIAL_ISSUE` records, not semantic decisions or repair authorization.

## Validate ingest coverage

After the selected parser actually runs, record what was extracted and what was not:

```bash
python scripts/validate_ingest.py ingest-report.json
```

A `PASS` report cannot contain declared uninspected structures. A `PARTIAL` report
must identify explicit gaps or limitations. A `FAIL` report blocks claims of
completed file coverage.

## Validate DBabel reports

```bash
python scripts/validate_report.py examples/audit_report.json
```

The validator checks recorded contract consistency and evidence/repair gating. It
does not verify that an external source is true or that a file was visually correct.

## Package regression

```bash
python -m py_compile scripts/*.py
python -m unittest discover -s tests -v
python scripts/check_package.py
```

After intentional package edits:

```bash
python scripts/check_package.py --write-manifest
python scripts/check_package.py
python -m unittest discover -s tests -v
git diff --check
```

## Data and privacy boundary

Local tooling should operate on the minimum material needed for the task. The format
probe does not authorize uploads or network calls. Optional third-party parsers may
have their own I/O, model, native-library, or service behavior; review those
properties before processing confidential or restricted material.

# Local tooling

[简体中文](LOCAL_TOOLING.zh-CN.md) · [Documentation index](INDEX.md)

DBabel's local scripts provide reproducible contracts around routing, format
preflight, glossary handling, deterministic QA, ingest coverage, and structured
reports. Use their structured outputs as inputs to Agent source reading and semantic review.

## Baseline environment

Core validation targets Python 3.9+ and uses only the dependencies in
`requirements-dev.txt`. Optional document parsers are not required for package
validation and are not installed automatically.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
```

## Optional integrations

```bash
python -m pip install -r requirements-integration.txt
```

This installs official OpenAI/Anthropic SDK transports on Python 3.10+, RapidFuzz similarity suggestions on Python 3.11+, and lxml for TMX exchange. The core remains usable on Python 3.9; SDK transport is selected automatically when available, and provider JSON can select `transport_backend: "stdlib"` or `"sdk"` explicitly. See [provider compatibility](PROVIDER_COMPATIBILITY.md) for protocol and streaming limits. The packaged macOS app includes these integrations.

## Check the provider and run a resumable translation

```bash
python scripts/check_provider_connection.py --provider-config provider.json --task-check
python scripts/run_project.py manual.docx --source-language zh-CN --target-language en --text-role PROSE --provider-config provider.json --project-id my-manual --product MyDatabase --product-version 1.0 --workspace-root output/runtime
python scripts/list_resumable_runs.py --workspace-root output/runtime
```

The task check uses one bounded synthetic request to verify the translation JSON contract, unit identity and protected literals. `TASK_READY` means that probe passed; `CONTRACT_FAILED` means the API responded but the contract failed. This may consume provider tokens. Without `--task-check`, the CLI performs the earlier connection-only probe.

Add `--resume-run output/runtime/RUN_<id>` to the same translation command to reuse verified artifacts and completed batches. Keep the source, language pair, provider identity and declared memory context unchanged. Discovery includes recoverable failed, interrupted and unfinished stage states; an active process owns an OS lock and excludes concurrent resume. See [scoped memory](LOCAL_PRECHECK_AND_MEMORY.md) for project IDs and document-hash fallback.

## TMX interchange and evidence cache

`scripts/tmx_exchange.py` imports plain TMX 1.4 as unapproved candidates or exports review/memory data. `scripts/evidence_cache.py` records source hashes, scope, expiry and dependent unit IDs, then reports affected units when evidence drifts or expires. Commands and provenance rules are in [interoperability and evidence](INTEROPERABILITY_AND_EVIDENCE.md).

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
used. Run extraction next and record its coverage.

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

For `TRANSLATE` / `BILINGUAL_REVIEW`, never feed a source-only anchor directly to bilingual QA. Materialize the review target first:

```bash
python scripts/prepare_review_qa.py aligned-units.json --mode TRANSLATE --output review-qa-units.jsonl --receipt qa-target-selection.json
```

After creating the `.dbreview` session with both `--qa-report` and `--audit-report`, validate the full human-review handoff:

```bash
python scripts/validate_translate_delivery.py project.en.dbreview --qa-input review-qa-units.jsonl --qa-report qa_report.json --audit-report audit-report.json --surface full --output delivery-receipt.json
```

A successful receipt means `READY_FOR_HUMAN_REVIEW`, not final completion.


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

The validator checks recorded contract consistency and evidence/repair gating. Review source validity and rendered layout separately.

## Package regression

```bash
python -m py_compile scripts/*.py
python scripts/run_tests.py
python scripts/check_package.py
```

After intentional package edits:

```bash
python scripts/check_package.py --write-manifest
python scripts/check_package.py
python scripts/run_tests.py
git diff --check
```

The test runner creates disposable memory, terminology-settings and rejection paths, protecting the user's live state. Optional browser and property jobs are described in [contributing](../CONTRIBUTING.md).

## Local files and services

The Full Local Workbench sends uploads to its authenticated local server at 127.0.0.1. Portable Review is a decisions-only fallback and does not provide glossary upload, fresh local QA or native export. New sessions save source copies in inputs/ and extraction details in intake.json. Agent and external parser services use the permissions supplied for the task.

## Review, checkpoint export and language-review handoff

```bash
python scripts/start_review_workbench.py project.dbreview --original target.docx --output reviewed.docx
python scripts/start_review_workbench.py project.dbreview --original target.xlsx --output reviewed.xlsx
python scripts/export_reviewed_document.py project.dbreview --original target.docx --output checkpoint-01.docx --export-mode CHECKPOINT --receipt checkpoint-01.json
python scripts/build_post_review_report.py project.dbreview --output post-review.json
```

Use a new output filename for each CLI export. `FINAL` is the default export mode; `CHECKPOINT` preserves pending content without approving it. Reports are available before all reviews finish. The handoff records Agent review as `NOT_RUN`; follow `docs/POST_REVIEW_QA.md` to perform the semantic review.

## Document intake and review-result delivery

```bash
python scripts/intake_document.py source.md --inspect
python scripts/intake_document.py source.md --source-language zh-CN --target-languages en,ja --output manual.multilingual.dbreview
python scripts/start_review_workbench.py manual.multilingual.dbreview
python scripts/export_review_results.py manual.multilingual.dbreview --format json --output manual.review.json
```

The desktop upload panel runs the same extraction path. The Terminology page validates uploaded glossary CSV/JSON and scores applicable approved terms. [Document formats](DOCUMENT_FORMATS.md) lists dependencies, extracted structures and output fidelity.

---
name: dbabel-database-terminology-audit
description: Verify database terminology, audit documents, review bilingual translations, translate with terminology constraints, and repair evidenced terminology errors. Use for database terminology and localization tasks; SQL debugging and database administration are outside this workflow.
metadata:
  version: "1.5.0"
---

# DBabel

DBabel is a progressive-loading workflow for database terminology and technical
localization. This file is the runtime kernel. Do not preload every file in
`references/`, `config/`, `schemas/`, `templates/`, or `examples/`.

All relative paths are resolved from this Skill folder.

## Choose the task

| Mode | Deliverable |
|---|---|
| `LOOKUP` | Term, concept, scope, decision, and supporting source |
| `AUDIT` | Located findings and coverage summary |
| `BILINGUAL_REVIEW` | Aligned source/target findings |
| `TRANSLATE` | Translation with terminology constraints and QA |
| `REPAIR` | Corrected copy, change log, and round-trip QA |
| `SOURCE_RESEARCH` | Evidence and remaining questions |
| `CLAIM_ROUTE` | Technical claims separated for verification |
| `GOVERNANCE` | Candidates for a user-controlled project glossary |

Combine modes only when the task requires it. `AUDIT` or `BILINGUAL_REVIEW` does
not authorize `REPAIR`.

## Kernel invariants

These rules always apply, including when a routed reference is not loaded:

1. DBabel is not a bundled terminology database. User/project terminology remains
   scoped runtime data.
2. A deterministic QA result is a `POTENTIAL_ISSUE`, not evidence, a semantic
   verdict, confidence, or repair authorization.
3. Worked examples are diagnostic patterns, never evidence for the current task.
4. Preserve literal SQL, identifiers, parameters, commands, paths, filenames,
   URLs, placeholders, formulas/macros, exact required UI labels, and other
   protected tokens unless a separately authorized change is supported.
5. Search snippets, AI summaries, and MT/LLM output cannot substantiate a
   terminology replacement. Open the underlying authoritative source when external
   evidence is required.
6. Preserve product/version/text-role scope and unresolved conflicts. Similar
   functionality across vendors does not establish terminological equivalence.
7. `REVIEW` is the correct decision when required context or evidence is missing.
8. Never describe an unrun check, partial extraction, proposed repair, or failed
   output as verified.
9. AI/MT suggestions, deterministic issues, and semantic findings are not human
   approval. When a requested bilingual change or native export requires human
   approval, materialize a Review Session and never fabricate an accepted review
   state on the user's behalf.

## Progressive execution

### 1. Build the task context

Record only facts supported by the request and available inputs: mode, languages,
product/version scope, project resources, research permission, repair state, and
material risk tags. Unknown facts remain unknown.

For reproducible local execution, `scripts/prepare_runtime.py` can build a validated
task context and resource plan.

### 2. Preflight files before parsing

For file inputs, determine content format and available parser capability before
ingestion. Do not trust the filename extension alone. Use the bounded format probe
and capability preflight in `scripts/preflight_document.py` when available, or an
equivalent runtime check.

A preflight result of `READY` means only that a parser/backend may be used. It does
not prove that text, structure, notes, tables, formulas, macros, images, or other
required content were successfully ingested.

### 3. Route instructions

Load `config/resource_router.yaml`, build the validated resource plan, and load only
the paths in `load_now`. Load only the worked-example sections listed in
`example_sections`. Do not perform a precautionary full-reference sweep.

Re-route when material state changes, including completion of source/target
alignment, discovery of a technical claim, failure of an approved source to resolve
a term, explicit research request, or repair authorization.

### 4. Ingest and validate coverage

After parsing a file, validate what was actually extracted. Record stable locations,
inspected structures, uninspected structures, warnings, and limitations. Use
`schemas/ingest_report.schema.json` and `scripts/validate_ingest.py` when producing a
machine-readable ingest gate.

`PASS` requires complete declared ingest coverage for the intended parser scope.
`PARTIAL` is usable only with explicit gaps. `FAIL` blocks claims of completed file
coverage.

### 5. Perform the routed task

Follow only the loaded task-specific policies. Resolve the narrowest reliable
context, classify material candidates, apply scoped user resources, research only
when needed/permitted, assess evidence, and adjudicate.

The decision vocabulary is:

- `KEEP`
- `REPLACE`
- `PROTECT`
- `REVIEW`
- `OUT_OF_SCOPE_CLAIM`

Confidence is `HIGH`, `MEDIUM`, `LOW`, or `REVIEW_REQUIRED`.

For `BILINGUAL_REVIEW` and `TRANSLATE`, explicit observed translation signals may be routed to candidate techniques with `scripts/suggest_translation_techniques.py`. Candidate routing uses exact catalog triggers plus applicable mode and concrete text role. A candidate is diagnostic routing metadata only: it is not evidence, a finding, a semantic decision, repair authorization, or human approval. Confirm the failure mode semantically before attaching a technique annotation to a finding.

`scripts/extract_translation_signals.py` may produce those observations from an allowlisted set of deterministic surface cues such as protected literals, explicit modal/scope markers, explicit condition or causal connectors, and declared text roles. The extractor records source/target/context provenance and never infers semantic-only triggers such as source conflicts, omitted antecedents, role reversal, polysemy, or cross-product equivalence. Missing language or text-role context must not be guessed.

### 6. Run bilingual QA only after alignment

When aligned source/target units exist, run applicable deterministic checks and then
semantic QA. Mechanical mismatch detection must never be promoted directly to
`REPLACE`.

### 7. Route approval-required changes through Review Workbench

When `BILINGUAL_REVIEW`, `TRANSLATE`, or `REPAIR` produces proposed target changes
that require user approval, or when native document export is requested after
review, materialize a `.dbreview` Review Session with
`scripts/create_review_session.py`.

The Agent may populate aligned units, findings, deterministic issues, evidence, and
suggested targets. Only the human reviewer may create the review decisions
`ACCEPT_SUGGESTION`, `KEEP_CURRENT`, `USER_EDITED`, `DEFERRED`, `BLOCKED`, or
`WAIVED`.

For local native export, start `scripts/start_review_workbench.py` with both
`--original` and `--output`. Review-only or Portable Review may omit a native output
path, but that mode must remain explicit. Never claim that native export is available
when the output path is not configured.

Portable decisions must be imported into the matching session and receive fresh QA
before native export.

### 8. Repair only through the repair gate

Apply a repair only when it is authorized and the finding is a located `REPLACE`
with HIGH confidence, adequate opened current evidence or an explicit scoped
project rule, no unresolved conflict, and a supported writing workflow. Confirm the
current span still matches before editing.

Protected literal changes require separate explicit authorization.

Write to a copy unless overwrite was explicitly requested. Reopen the result and
perform round-trip QA. A successful save is not a verified repair.

## Evidence minimum

Use user-approved scoped resources first. Research unresolved, conflicting,
version-sensitive, or explicitly requested questions when permitted. Match source
authority to the claim: standards for standardized concepts; same-product/version
vendor material for vendor terminology; same-version localized UI for exact labels.

Do not invent missing source metadata. Distinguish a project wording preference
from an official vendor designation.

## Output and status

Report inspected and uninspected scope, located findings, evidence, QA actually
performed, unresolved items, and repair outcomes. Validate structured reports with
`scripts/validate_report.py` when the validation runtime is available.

Finish with one status:

- `COMPLETED`: requested scope and applicable QA finished; no unresolved review item.
- `COMPLETED_WITH_REVIEW`: useful output with explicit review items, routed claims,
  partial coverage, or unavailable checks.
- `BLOCKED`: missing input, verified format, parser capability, or other essential
  prerequisite prevents the requested deliverable.
- `FAILED`: attempted processing or repair failed validation.

Detailed rules are loaded progressively through the resource router. If repository
instructions conflict, this kernel is authoritative for DBabel workflow behavior.

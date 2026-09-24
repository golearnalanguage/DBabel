# Output and data contracts

Use concise prose or a table for small lookups. Use the audit report schema when
JSON is requested or useful for downstream review. Runtime plans, ingest reports,
project glossaries, bilingual units, and deterministic QA reports have separate
schemas and must not be presented as audit-report findings unless the semantic
workflow actually adjudicated them.

## Audit report 1.5.0

The 1.5 package keeps the compatible audit-report structure introduced in 1.3
and retained in 1.4. The `dbabel_version` field records the DBabel package version
that produced the report. The current validator accepts `1.3.0`, `1.4.0`, and
`1.5.0` reports; newly produced v1.5 reports should use `1.5.0`.

- `mode` identifies the primary task; `secondary_modes` records combined tasks.
- `status` describes completion, independently of individual terminology decisions.
- `coverage` lists inspected and uninspected scope with FULL, PARTIAL, or NONE status.
- `findings` use unique IDs, exact locations, original text, text role, class,
  decision, confidence, reason, protection flag, and evidence references.
- `verification_required` is true for explicitly requested or high-risk verification.
  A verified KEEP requires suitable opened evidence just as REPLACE does.
- `sources` contains evidence records keyed by unique `id`; every `evidence_refs`
  entry resolves to one of these IDs. Use an empty array when no source was read.
- `qa` records performed checks and PASS, PARTIAL, FAIL, or NOT_RUN status.
- `repair` records authorization, status, output path, changes keyed by finding ID,
  and round-trip QA. Use NOT_REQUESTED when no repair was requested; use PROPOSED
  for unapplied changes, BLOCKED for missing prerequisites, APPLIED for an
  unverified copy, VERIFIED after passing QA, and FAILED for a failed attempt.
- `limitations` and `next_actions` explain incomplete or review outcomes.
- `searches`, `glossary_candidates`, and `output_documents` are optional task outputs.

Each changed occurrence has its own finding ID. A change must match its finding's
location, original text, and recommended text. Before applying it, check that the
source span is still current. `literal_change_authorized` is required for an
applied change to a protected literal.

Use YYYY-MM-DD retrieval dates. Omit unknown optional scope fields. Evidence state
CURRENT means applicable to the target scope, including historical product versions.
Search snippets and unread sources remain insufficient for a replacement.

A report may be structurally valid while containing a FAILED or BLOCKED task.
Validation checks the consistency of that outcome; it does not turn it into success.

## Related v1.5 machine contracts

These contracts serve different stages and must remain distinct:

- `schemas/task_context.schema.json` — facts known at routing time;
- `schemas/resource_plan.schema.json` — instructions selected for progressive load;
- `schemas/document_probe.schema.json` and `schemas/document_preflight.schema.json`
  — content format and parser/backend readiness;
- `schemas/ingest_report.schema.json` — actual extraction coverage after parsing;
- `schemas/project_glossary.schema.json` — user-controlled project terminology;
- `schemas/bilingual_unit.schema.json` — already aligned source/target units;
- `schemas/deterministic_qa_report.schema.json` — mechanical `POTENTIAL_ISSUE`
  results, not semantic decisions or repair authorization;
- `schemas/translation_techniques.schema.json` — machine-readable technical
  translation technique and controlled-transformation registry.

A successful preflight does not imply successful ingest. A clean deterministic QA
report does not establish semantic correctness. A deterministic issue does not by
itself justify `REPLACE` or authorize editing.

## Validate

Install `requirements-dev.txt`, then run:

```bash
python scripts/validate_report.py examples/audit_report.json
```

The validator resolves schemas locally and checks cross-record invariants. Source
truth, extraction completeness, and document integrity still require actual review.

Package-level validation additionally checks that the report producer version,
README version, configuration versions, resource/example routers, glossary CSV
header, workflow safety invariants, and format-backend references remain mutually
consistent:

```bash
python scripts/check_package.py
```

## Compatibility and migration

Version 1.5 deliberately accepts structurally valid 1.3 and 1.4 audit reports
because the 1.5 release does not require rewriting earlier compatible reports. Do
not rewrite an old report's `dbabel_version` merely to make it look current; that
field identifies the producer version.

Version 1.2 reports still require migration to the 1.3/1.4/1.5-compatible structure
because 1.3 added required completion, coverage, QA, repair, source records, and
finding IDs.
Upgrade an older report by recording the work actually performed; do not invent
evidence or mark skipped checks as passed.

# Output and data contracts

Use concise prose or a table for small lookups. Use the audit report schema when
JSON is requested or useful for downstream review.

## Report 1.3.0

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

## Validate

Install `requirements-dev.txt`, then run:

```bash
python scripts/validate_report.py examples/audit_report.json
```

The validator resolves schemas locally and checks cross-record invariants. Source
truth, extraction completeness, and document integrity still require actual review.

## Migrating 1.2 reports

Version 1.3 adds required completion, coverage, QA, repair, source records, and
finding IDs. Upgrade a 1.2 report by recording the work actually performed; do not
invent evidence or mark skipped checks as passed. Old reports need these additions
to validate against the 1.3 contract.

# DBabel Review Workbench

Current DBabel Skill/package version: **1.5.0**.

Current Review Workbench version: **1.5.0**.

The Review Workbench is part of the DBabel v1.5.0 release contract. A repository
version change does not by itself create or move a Git tag or GitHub Release;
those release artifacts are created only after validation succeeds.

The Review Workbench adds a human approval layer between DBabel findings/QA and any
native-format repair. It is intentionally not a full CAT platform.

## Invariants

- A DBabel suggestion is not user approval.
- `POTENTIAL_ISSUE` remains a deterministic QA classification, not a semantic error verdict.
- `USER_EDITED` content is rechecked before export.
- `UNREVIEWED`, `DEFERRED`, and `BLOCKED` units prevent final export; checkpoint export preserves their original content and lists them as pending.
- A remaining deterministic `ERROR` prevents export unless the user explicitly chooses
  `WAIVED`, records a non-empty reason, and the waiver matches the current stable issue
  fingerprint.
- The original document SHA-256 must still match the review session before native export.
- Native export requires every included review unit to have `ALIGNED` bilingual alignment.
  `AMBIGUOUS`, `SPLIT`, `MERGED`, and `UNALIGNED` units remain reviewable but
  block native write-back until a dedicated alignment/write-back path exists.
- The original document is never overwritten.
- A written output is not `VERIFIED` until round-trip checks pass.

## Review bundle

A `.dbreview` directory contains review metadata and decisions, not a second copy of the
customer document by default:

```text
Manual.dbreview/
  session.json
  units.jsonl
  issues.json
  evidence.json
  decisions.json
  events.jsonl
  anchors.json
  original.sha256
```

The local path of the original is not stored unless the creator explicitly requests a
path hint.

## Bilingual DOCX alignment

The default extractor remains fail-closed and positional. If source and target
non-empty paragraph counts differ, DBabel does not guess an alignment.

For real bilingual documents that contain split or merged paragraphs, use an
explicit alignment map.

The map uses `format_version` `1.0` and an `alignments` array. Each alignment
entry contains a stable `id`, 1-based `source` paragraph indexes, 1-based
`target` paragraph indexes, and one of these states:

- `ALIGNED`: exactly 1 source paragraph to 1 target paragraph.
- `SPLIT`: exactly 1 source paragraph to multiple target paragraphs.
- `MERGED`: multiple source paragraphs to exactly 1 target paragraph.
- `UNALIGNED`: exactly one unmatched paragraph on one side.
- `AMBIGUOUS`: content exists on both sides but the mapping requires human
  resolution.

Every non-empty source and target paragraph must be represented exactly once.
Missing coverage, duplicate consumption, out-of-range indexes, or alignment
states that do not match their source/target cardinality fail closed.

DBabel does not infer `SPLIT`, `MERGED`, `UNALIGNED`, or `AMBIGUOUS`
relationships automatically. Those relationships must be explicitly supplied.

The extractor records `alignment_id`, `source_refs`, and `target_refs` in review
units so the mapping remains auditable after `.dbreview` creation.

Only `ALIGNED` units can participate in native DOCX write-back. Other alignment
states remain reviewable but cannot be included in native write-back.

## Desktop workflow

```bash
python scripts/create_review_session.py units.jsonl \
  --qa-report qa-report.json \
  --audit-report audit-report.json \
  --original translated.docx \
  --output translated.dbreview

python scripts/start_review_workbench.py translated.dbreview \
  --original translated.docx \
  --output translated.reviewed.docx
```

The server binds only to `127.0.0.1`, chooses an available port, uses a random session
token, sends restrictive browser security headers, and has no external frontend runtime.

## Portable workflow

```bash
python scripts/build_portable_review.py translated.dbreview \
  --output translated-review.html
```

The generated HTML is self-contained and makes no network requests. It can export a
`decisions.json` file, which is imported on a machine that has the review bundle:

```bash
python scripts/import_review_decisions.py \
  translated.dbreview translated.docx.decisions.json
```

Portable review never writes the native document itself.

## DOCX native export

The initial native adapter supports `.docx` only. It uses exact OOXML paragraph anchors,
verifies the original package hash and anchor text, patches existing `w:t` nodes rather
than rebuilding the document, refuses ambiguous anchors, refuses in-place overwrite,
and verifies reviewed target text plus non-target paragraph text after writing.

```bash
python scripts/export_reviewed_document.py translated.dbreview \
  --original translated.docx \
  --output translated.reviewed.docx \
  --receipt export-receipt.json
```

DOCM/PPTX/XLSX/PDF native repair is not claimed by the current native adapter.

For DOCX, ordinary paragraph text inside tables, hyperlinks, and content
controls is extractable and covered by regression tests. Paragraphs containing
Word field codes or tracked revisions remain reviewable, but native write-back
is blocked because editing their displayed `w:t` text can invalidate Word's
field/revision semantics.

## Workspace behavior and appearance

Desktop and Portable Review share local CSS and the same session views. Navigation opens review, terminology findings, linked evidence, QA, reports and project settings. Activity shows recorded decisions and notes. Terminology is a session overview, not a project glossary editor; settings show session metadata and local display preferences.

Use status, issue, location and tag filters to narrow the table. Select one page or all matching units before an explicit bulk Keep Current / Defer decision. Compact mode changes row spacing while preserving complete sentence text. Close the inspector to widen the table; select a row to reopen it.

System / Dark / Light follow the selected browser preference. The glass shell uses restrained borders and semantic status colors; the review text stays fully readable. Small screens retain navigation and stack the inspector below the table. Assets, scripts and styles load locally. No fabricated account identity or operating-system controls are displayed.

## Technique-aware review findings

Semantic review issues may include a translation-technique annotation containing
the technique ID, catalog risk, controlled transformations, semantic quality
dimensions, and a concise trigger reason.

Desktop and Portable Review expose this metadata in the Suggestion inspector as
diagnostic context. It explains why DBabel surfaced the finding; it does not add a
new human-decision state, convert deterministic QA into a semantic verdict, or
authorize repair.

Human decisions remain `UNREVIEWED`, `ACCEPT_SUGGESTION`, `KEEP_CURRENT`,
`USER_EDITED`, `DEFERRED`, `BLOCKED`, and `WAIVED`.

## Staged delivery and language review

The desktop and portable workbenches provide session-backed Terminology, Evidence, Quality Check, Reports, Project Settings and Activity views. Location/tag filters, selectable page size, compact rows and inspector close/reopen work locally. Terminology shows session findings and labels, not a glossary editor. Project settings expose session metadata and local display preferences.

Desktop export accepts `FINAL` (default) or `CHECKPOINT`. A checkpoint applies completed human decisions only, preserves unresolved content and lists omitted unit IDs in `review_scope`. ERRORs in the included scope, original hash mismatch and invalid anchors still block. No pending decision becomes approved. Both modes use a new output path; existing output files are never overwritten. The Workbench numbers checkpoint copies and their receipts automatically. The CLI requires a new output filename for each export; final export retains the configured output path.

```bash
python scripts/export_reviewed_document.py project.dbreview --original target.docx --output checkpoint-01.docx --export-mode CHECKPOINT --receipt checkpoint-01.json
python scripts/build_post_review_report.py project.dbreview --output post-review.json
```

Reports are available without finishing all reviews. Follow [post-review QA](POST_REVIEW_QA.md) for spelling and word-use suggestions after human edits. This creates an Agent handoff, not an automatic AI review service. Portable review still exports decisions for import and fresh local QA.

# DBabel Review Workbench

[简体中文](REVIEW_WORKBENCH.zh-CN.md) · [Documentation index](INDEX.md)

For local offline use, begin with [the reviewer walkthrough](WORKFLOW_GUIDE.md).
Uploaded single-target DOCX/TXT/MD/XLSX sessions configure native delivery automatically.
Export downloads a ZIP with the document, receipt, bilingual HTML and Markdown/JSON
handoff. Source-only input is an unreviewed working copy until translated and reviewed.
Original-format delivery preserves structure; inspect rendered wrapping and pagination.

Current DBabel Skill/package version: **1.5.0**.

Current Review Workbench version: **1.5.0**.

The Review Workbench is part of the DBabel v1.5.0 release contract. A repository
version change does not by itself create or move a Git tag or GitHub Release;
those release artifacts are created only after validation succeeds.

The Workbench connects source/target text, proposed changes, evidence and human decisions. **Full Local Review Workbench** means the local desktop/server surface with project-glossary upload, scoped terminology scoring, evidence/issues, fresh QA, six review-result formats and configured native export. **Portable Review** is an offline fallback for decisions exchange only; it is not capability-equivalent to the Full Local Workbench. Both interfaces support English and Simplified Chinese. In `TRANSLATE` / `BILINGUAL_REVIEW`, `suggested_target` is presented as an explicitly unapproved proposal until a human decision creates `approved_target`.

Start with the [Chinese walkthrough](WORKFLOW_GUIDE.zh-CN.md) for complete executable commands. Consult the [format matrix](DOCUMENT_FORMATS.md) for parser dependencies, extraction coverage and export fidelity.

## Review and export rules

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

A `.dbreview` directory created from aligned units contains:

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

Aligned-unit sessions record the original filename and hash; `--include-path-hint` also records its local path. Upload-created sessions additionally store input copies in `inputs/` and extraction coverage in `intake.json`. Uploaded glossaries are saved as `project-glossary.csv` or `project-glossary.json`.

## Bilingual DOCX alignment

The DOCX alignment extractor pairs non-empty paragraphs by position and validates coverage. If source and target
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

Before creating a translation review session, materialize the deterministic-QA target from the actual proposal instead of the source anchor:

```bash
python scripts/prepare_review_qa.py aligned-units.json --mode TRANSLATE --output review-qa-units.jsonl --receipt qa-target-selection.json
python scripts/check_bilingual_integrity.py review-qa-units.jsonl --output qa-report.json
```

After session creation, `scripts/validate_translate_delivery.py ... --surface full` must pass. The successful stage is `READY_FOR_HUMAN_REVIEW`, not final completion.


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

## Native export

Native delivery supports DOCX, TXT, Markdown and XLSX. The DOCX adapter uses exact OOXML paragraph anchors,
verifies the original package hash and anchor text, patches existing `w:t` nodes rather
than rebuilding the document, refuses ambiguous anchors, refuses in-place overwrite,
and verifies reviewed target text, non-target paragraph text, non-text XML and untouched
package parts after writing. TXT/Markdown use line anchors and retain UTF-8 BOM,
original newline sequences, blank lines and untouched lines. All supported native formats produce
a receipt, bilingual HTML and Markdown/JSON Agent handoff alongside the native copy.

```bash
python scripts/export_reviewed_document.py translated.dbreview \
  --original translated.docx \
  --output translated.reviewed.docx \
  --receipt export-receipt.json
```

DOCM/PPTX/PDF native repair is not implemented. XLSX native write-back is available for
resolved cell anchors: DBabel patches approved cell elements in a new workbook and
verifies untouched OOXML part payloads byte-for-byte. PPTX/PDF intake remains
review-result-only. See the [format matrix](DOCUMENT_FORMATS.md).

For DOCX, ordinary paragraph text inside tables, hyperlinks, and content
controls is extractable and covered by regression tests. Paragraphs containing
Word field codes, tracked revisions, nested paragraphs, manual breaks or tabs remain
reviewable, but the current adapter blocks rewriting those paragraphs. Other
parts remain unchanged. Preserving formatting definitions does not guarantee the
same rendered line breaks or pagination; inspect the output in Word or LibreOffice.

## Workspace behavior and appearance

Desktop and Portable Review share local CSS and the same session views. Navigation opens review, terminology findings, linked evidence, QA, reports and project settings. Activity shows recorded decisions and notes. The desktop Terminology page uploads and validates project glossary CSV/JSON, lists mismatches and reports lexical compliance. Settings show session metadata and display preferences.

Use status, issue, location and tag filters to narrow the table. Select one page or all matching units before an explicit bulk Keep Current / Defer decision. Compact mode changes row spacing while preserving complete sentence text. Close the inspector to widen the table; select a row to reopen it.

System / Dark / Light follow the selected browser preference. The table and inspector scroll independently on desktop; filters remain accessible in the left pane. Small screens retain navigation and stack the inspector below the table. Assets, scripts and styles load locally. Language and theme controls remain available at mobile widths.

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

The desktop and portable workbenches provide session-backed Terminology, Evidence, Quality Check, Reports, Project Settings and Activity views. Location/tag filters, selectable page size, compact rows and inspector close/reopen work locally. Terminology shows findings, labels and the local glossary upload/score panel. Project settings expose session metadata and local display preferences.

Desktop export accepts `FINAL` (default) or `CHECKPOINT`. A checkpoint applies completed human decisions only, preserves unresolved content and lists omitted unit IDs in `review_scope`. ERRORs in the included scope, original hash mismatch and invalid anchors still block. No pending decision becomes approved. Both modes use a new output path; existing output files are never overwritten. The Workbench numbers checkpoint copies and their receipts automatically. The CLI requires a new output filename for each export; final export retains the configured output path.

```bash
python scripts/export_reviewed_document.py project.dbreview --original target.docx --output checkpoint-01.docx --export-mode CHECKPOINT --receipt checkpoint-01.json
python scripts/build_post_review_report.py project.dbreview --output post-review.json
```

Reports are available without finishing all reviews. Follow [post-review QA](POST_REVIEW_QA.md) for spelling and word-use suggestions after human edits. This creates an Agent handoff, not an automatic AI review service. Portable review still exports decisions for import and fresh local QA.

## Upload and review-result export

Choose **Upload documents** in the left navigation. Inspect the source, set explicit language tags and create a session. Uploading a target requires a single target language and equal segment counts; select the alignment checkbox only after checking correspondence. Multiple target languages create separate pending units. An Agent supplies translations and reasons through aligned-unit JSON; the server does not call a model.

Use **Download review results** at any stage. Review-only and demo sessions export JSON, CSV, TSV, Markdown, HTML and TXT, including pending rows and explicit decisions. JSON additionally retains suggestions, issues, evidence and reviewer notes. See [format fidelity](DOCUMENT_FORMATS.md#working-copies-and-bilingual-results).

```bash
python scripts/intake_document.py source.txt --inspect
python scripts/intake_document.py source.txt --source-language zh-CN --target-languages en,ja --output manual.multilingual.dbreview
python scripts/export_review_results.py manual.multilingual.dbreview --format html --output manual.review.html
```

## Suggestions and glossary scoring

Every unit shows either a proposed target with its reason or an actionable review instruction. Missing target text prompts translation in the declared target language. Findings produce a revision checklist; a unit without findings displays its current text and asks the reviewer to verify conditions, terminology and protected tokens. **Accept Suggestion** requires an actual `suggested_target`; guidance alone cannot be accepted as a translation.

Upload a canonical project glossary under **Terminology → Upload project glossary**. Word/PDF terminology documents should first be converted by an Agent to the DBabel CSV/JSON contract. The score counts passed applicable approved term/unit checks over all such checks; no applicable checks produce `null`, displayed as unavailable. It measures scoped lexical compliance. New decisions and fresh QA use the saved glossary; restarting the same session reloads it.

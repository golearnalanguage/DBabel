# DBabel runtime stage guide

Read only the section for the current stage. The [Skill kernel](../SKILL.md) defines shared invariants.

## Workflow

### 1. Establish context and preflight

Record task mode, source/target languages, product/version, user resources, research permission and repair authorization. Leave unsupported facts unknown. For reproducible context and routing:

```bash
python scripts/prepare_runtime.py --mode AUDIT --file manual.docx --declare-backend native_agent --output runtime-plan.json
```

Probe file content and available capabilities before parsing. A `READY` or `READY_FOR_INGEST` result identifies a usable parser; extraction still needs to run. For upload extraction and result-format choices, read [document formats](../docs/DOCUMENT_FORMATS.md). Use `scripts/intake_document.py --inspect` to obtain located text and declared omissions from the built-in intake path.

### 2. Route and ingest

Use `config/resource_router.yaml` and `scripts/route_resources.py`. Load only `load_now` and the independent cases in `example_files` (stable IDs remain in `example_sections`). Re-route after alignment, a newly discovered claim, unresolved evidence or a change in repair authorization.

Record stable locations, extracted structures and uninspected content. Validate machine-readable coverage with `schemas/ingest_report.schema.json` and `scripts/validate_ingest.py`. `PASS` covers the declared scope; `PARTIAL` includes specific gaps; `FAIL` requires fixing extraction before claiming completion.

For bilingual DOCX, use `scripts/extract_docx_bilingual_units.py`. Explicit maps represent split, merged, ambiguous and unmatched paragraphs. For multilingual review, create a separate unit per source/target-language pair; do not mix several translations inside one target string.

### 3. Resolve terms and propose wording

Resolve the narrowest supported context, classify the candidate, consult scoped user resources and research unresolved claims when permitted. Decisions are `KEEP`, `REPLACE`, `PROTECT`, `REVIEW` and `OUT_OF_SCOPE_CLAIM`. Confidence values are `HIGH`, `MEDIUM`, `LOW` and `REVIEW_REQUIRED`.

Each review unit must give the reviewer something actionable:

- When proposing a translation, set `suggested_target` to the complete target text and `suggestion_reason` to the specific linguistic or terminology rationale. Preserve `target` as the current text.
- For long documents, preserve each occurrence of every protected literal. If a model drops one, retry the affected unit with its exact required count. A structurally valid suggestion that still misses a literal may enter the Workbench only as `REVIEW`, with the mismatch named in `suggestion_reason` and a deterministic QA error. It remains unapproved and must be corrected and rechecked before export.
- When the current wording is sound, explain what was checked and propose keeping it. Human confirmation remains pending.
- When context is missing, state the exact question and the evidence needed; do not insert an invented translation.
- For deterministic mismatches, name the literal, number, condition or terminology rule to inspect. A generic “review required” alone is insufficient.

`scripts/create_review_session.py` preserves `suggested_target` and `suggestion_reason` from aligned units. Findings in an audit report can also produce located proposals. The UI supplies per-unit revision guidance for older sessions without suggestions.

### 4. Validate glossary and QA

Load glossary JSON/CSV through `scripts/validate_glossary.py`. Convert terminology documents to the canonical template when needed, retaining source language, target language, scope, approval and provenance notes. User approval determines `PROJECT_APPROVED`; extraction alone does not approve an entry.

Only applicable approved entries affect checks. The Workbench's Terminology page accepts uploads and reports passed term/unit checks divided by all applicable checks. Missing applicable terms yield no score. Use the score for glossary compliance, and perform semantic review separately.

After alignment, materialize the actual target under review before deterministic QA:

```bash
python scripts/prepare_review_qa.py aligned-units.json --mode TRANSLATE \
  --output review-qa-units.jsonl --receipt qa-target-selection.json
python scripts/check_bilingual_integrity.py review-qa-units.jsonl \
  --output qa-report.json
```

`prepare_review_qa.py` fails closed when a cross-language unit would compare the source with an identical source anchor unless the unit is explicitly `KEEP` / `PROTECT`. Then inspect meaning and evidence. `scripts/build_translation_review_intake.py` combines surface observations, technique candidates and applicable QA. PRE_TRANSLATION hands off to TRANSLATION; bilingual/post-translation intake hands off to ADJUDICATION. Candidate techniques become formal finding metadata only after semantic assessment. Load `references/18_TECHNICAL_TRANSLATION_PLAYBOOK.md` through the translation-mode router when needed.

### 5. Create and open a review session

```bash
python scripts/create_review_session.py aligned-units.json --output manual.en.dbreview
python scripts/start_review_workbench.py manual.en.dbreview --glossary project_glossary.csv
```

For a real translation handoff, create the session with the actual `--qa-report` and `--audit-report` so deterministic issues, evidence and glossary candidates are bound into `.dbreview`, then run the delivery gate:

```bash
python scripts/create_review_session.py aligned-units.json \
  --qa-report qa-report.json --audit-report audit-report.json \
  --output manual.en.dbreview --mode TRANSLATE
python scripts/validate_translate_delivery.py manual.en.dbreview \
  --qa-input review-qa-units.jsonl --qa-report qa-report.json \
  --audit-report audit-report.json --surface full \
  --output delivery-receipt.json
```

Do not stop at `.dbreview` data or `export_review_results.py`. The handoff is only `READY_FOR_HUMAN_REVIEW` after the Full Local Workbench delivery gate passes. If the execution environment cannot expose a local server, deliver the `.dbreview` bundle and exact `start_local.py` / `start_review_workbench.py` command. A Portable Review HTML may be included only as an explicitly labelled fallback; it is not capability-equivalent to the Full Local Workbench.

For anchored DOCX export, add `--original target.docx` when creating the session, and launch with both `--original target.docx` and `--output target.reviewed.docx`. Keep the same original file throughout review.

For a person starting locally, use `scripts/start_local.py`, with an absolute script path when their current directory is unknown. It resumes a separate demo copy or the supplied `--bundle`. Explain the printed local URL, terminal lifetime and offline operation. The Workbench itself does not generate translations.

When preserving layout, use a single target language per native document. Source-only DOCX/TXT/MD intake retains source text as the unreviewed working copy; that text is an anchor, not a translation. Preserve it in `target` and put proposed translations in `suggested_target`. Use the identical original file when creating a new proposal session. Never turn an empty target into an ungrounded native anchor.

Use this delivery constraint in the task prompt when requested:

```text
For FINAL, replace only approved text in a new copy of the original file. For DRAFT,
replace each aligned unit with its approved text or pending suggested translation;
mark pending decisions in the receipt and handoff, never as approved. Preserve paragraph,
table, cell and formatting structure; do not insert lists or new paragraph breaks.
For specifications, preserve object, quantity, unit, comparator, modal force and
scope, using concise attribute/value wording inside existing structures.
Keep source and target languages separate and explain every proposal. Retain
human decisions and notes. Report extraction gaps, changed/unchanged/pending IDs,
checks actually performed and the visual review still needed. Deliver the native
copy, bilingual comparison, receipt and Markdown/JSON Agent handoff. Do not claim
pixel-identical pagination from text or XML checks alone.
```

The reviewer checks proposals, edits text, records decisions and reruns QA. Preserve existing decisions and notes during further Agent work. Import Portable Review decisions into the matching session and run fresh local QA.

A human rejection may record the rejected wording and its reason in the session.
For future proposals in the same language direction, never repeat that wording
for the same source segment. Short source/target term pairs also apply inside
longer segments containing the source phrase. This memory prohibits one
rendering; it does not approve an alternative or create a project glossary
entry. Keep the record with the session and allow explicit removal. If the
provider repeats it after bounded retries, route the unit to human revision.

The macOS Workbench keeps a session-scoped chat beside the selected unit. The reviewer may quote source and target, ask for the translation rationale, add a document or image, and continue the same conversation. Keep the selected unit ID and source/target context in each answer; distinguish a rule or located reference from an inference. A model's chat answer is not a human decision, cited authority, or QA result. Retain chat history with the session and return to the actual review decision controls for acceptance or editing. The browser-search shortcut opens the system default browser; inspect original sources before citing them as evidence.

### 6. Deliver results and verify native copies

All local sessions, including review-only and trial sessions, can export a review snapshot:

```bash
python scripts/export_review_results.py manual.en.dbreview --format json --output manual.review.json
```

JSON retains decisions, revisions, issues and evidence. CSV/TSV/Markdown/HTML/TXT provide bilingual or multilingual review documents with explicit statuses. Pending targets remain unchanged; unaccepted proposals stay proposals.

Native DOCX/TXT/MD/XLSX export uses exact anchors, the original hash and output verification. XLSX write-back patches anchored worksheet cells and worksheet tab names, updates print-area references for renamed tabs, and verifies that untouched OOXML part payloads remain byte-identical; formula cells are not rewritten, and tab renames referenced by worksheet formulas are rejected. DOCX additionally compares non-text XML and untouched package parts. `DRAFT` writes approved text or pending suggestions into every aligned unit, including unreviewed units; the resulting document has no review annotations. Its `DRAFT_EXPORTED` receipt lists pending decisions and records that fresh QA was not run for that export. `CHECKPOINT` applies completed decisions and leaves pending text unchanged; `FINAL` requires all necessary reviews and fresh QA. Deliver the receipt, bilingual HTML and Markdown/JSON handoffs beside the native copy. Explain what changed, what remained and what was excluded. Write to a new file, then inspect layout when publication fidelity matters. For a repair finding, require a located `REPLACE`, HIGH confidence, adequate current evidence or an explicit scoped project rule, and resolved conflicts before applying the authorized change.

### 7. Recheck human edits with an Agent

Create a revision-bound handoff with `scripts/build_post_review_report.py` and load [post-review QA](../docs/POST_REVIEW_QA.md). Check typos, word misuse, omission, terminology and protected tokens against current texts. Return locations, revisions, hashes, before/after wording and reasons. Review accepted suggestions again, then rerun QA before final export.

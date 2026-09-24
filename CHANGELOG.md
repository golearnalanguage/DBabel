# Changelog

## Unreleased

- Added a Translation Review Intake orchestration contract that composes surface extraction, signal contrasts, technique candidate routing, and phase-aware deterministic QA without creating semantic findings or approval.

- Added provenance-aware deterministic raw-text signal extraction for an allowlisted subset of Technical Translation Playbook triggers, while keeping semantic-only triggers outside regex-based automation.

- Added catalog-driven Technique Candidate Routing for explicit unit-level translation signals, with exact trigger matching, mode/text-role filtering, unmatched-signal reporting, and machine-enforced non-authoritative boundaries.

- Added technique-aware semantic review findings and Desktop/Portable Workbench explainability for technique risk, controlled transformations, quality dimensions, and trigger reasons without changing human decision semantics.

- Added a routed Technical Translation Playbook with 15 maintainable database and
  technical-localization techniques, controlled transformation risks, synthetic
  bilingual examples, and machine-readable technique contracts.
- Added cross-contract validation between translation techniques, deterministic QA,
  and progressive resource routing.
- Corrected the output/data-contract documentation to reflect v1.5 report
  compatibility.


## 1.5.0 — 2026-09-25

- Added DBabel Review Workbench for explicit human-in-the-loop bilingual review.
- Added `.dbreview` Review Sessions, review schemas, evidence/issues/decision
  contracts, and local/portable review surfaces.
- Added DOCX native export with Export Gate, original-file hashing, anchor checks,
  non-destructive output, and round-trip verification.
- Bound Portable Review decision exports to their originating Review Session and
  made malformed or cross-session imports fail closed.
- Prevented bilingual DOCX extraction from silently dropping unmatched paragraphs
  when source/target paragraph counts differ.
- Added an Agent-to-Workbench handoff contract so suggestions and findings never
  become fabricated human approval.
- Added explicit review-only versus native-export mode feedback.
- Added explicit auditable DOCX alignment maps for `ALIGNED`, `SPLIT`, `MERGED`,
  `UNALIGNED`, and `AMBIGUOUS` relationships, with complete paragraph coverage
  checks and fail-closed native write-back for non-`ALIGNED` units.
- Strengthened DOCX anchors with Word `w14:paraId` identity and fail-closed
  behavior when a previously anchored paragraph ID disappears.
- Added DOCX structure guards for field codes and tracked revisions while
  regression-testing paragraph extraction inside tables, hyperlinks, and
  content controls.
- Made desktop bulk review updates transactional, preserved reviewer notes,
  prevented hidden selections from leaking across filters/pages, and retained
  safe local bulk behavior in Portable Review.
- Removed or explicitly disabled remaining inactive Workbench controls and
  completed Portable Review copy/theme compatibility hardening.

## 1.4.0 — 2026-09-24

- Added a scope-aware project glossary layer with JSON/CSV normalization,
  validation, `PROJECT_APPROVED`-only enforcement, and explicit `PROTECT` behavior.
- Added deterministic bilingual QA for protected literals, placeholders, URLs,
  paths, filenames, CLI options, environment variables, versions, numbers,
  number/unit pairs, forbidden terms, and preferred/admitted project terms.
- Added machine-readable bilingual-unit and deterministic-QA-report contracts plus
  dedicated regression fixtures.
- Added semantic routing for the technical-translation worked examples so agents can
  load only matching sections instead of reading the whole example file.
- Refactored `SKILL.md` into a compact runtime kernel and added progressive resource
  routing with validated Task Context and Resource Plan contracts.
- Added bounded content-based file-format probing, extension/content conflict
  handling, macro-enabled Office detection, capability probing, and an optional
  backend registry without making third-party parsers mandatory dependencies.
- Added runtime-plan preparation and ingest-coverage validation so parser selection,
  successful extraction, full coverage, semantic QA, and verified repair remain
  separate claims.
- Expanded Python 3.9 regression coverage after identifying an API-compatibility gap
  that Python-3.11-only CI would not have caught.
- Preserved the data-light architecture: DBabel still ships no vendor termbase or
  vendor documentation corpus, and deterministic findings still do not authorize
  semantic replacement or repair.

## 1.3.0 — 2026-09-23

- Added installation and invocation instructions for Codex, Claude Code, and other agents, with an accompanying Chinese guide.
- Moved Skill version metadata into standard frontmatter and added Codex display metadata.
- Closed the review workflow with translation, coverage, QA feedback, and final reporting after repair verification.
- Connected findings to source records and added repair outcomes and completion status to the report contract. Version 1.2 reports require migration to the 1.3 schema.
- Added offline report validation, regression tests, synthetic workflow fixtures, and macOS/Linux CI.
- Removed owner-only GitHub setup, repository metadata, publishing checklist, and pre-publication licensing guidance.
- Refreshed the package manifest and packaged the complete Skill for installation.

## 1.2.0
- Prepared the repository for public GitHub release.
- Adopted PolyForm Noncommercial License 1.0.0 for noncommercial use.
- Added `LICENSE`, `NOTICE`, `DISCLAIMER.md`, and explicit license policy.
- Added a concise project code of conduct and release notes.
- Clarified that DBabel is source-available/noncommercial rather than OSI-approved open source.
- Retained the data-light architecture: DBabel ships workflow and evidence rules, not a terminology database.

## 1.1.0
- Renamed/reframed the package as DBabel.
- Made the core contract explicitly data-light: DBabel ships no terminology database or vendor corpus.
- Replaced "internal termbase first" with user-resource-first + authoritative runtime research.
- Added strict search-source-opening requirements.
- Added minimized-query privacy rules.
- Added project-local glossary candidate lifecycle without global approval.
- Added search-record schema and retrieval strategy.
- Added security and third-party notices.

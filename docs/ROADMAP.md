# Roadmap

The roadmap tracks the review workflow, schemas, validators, document adapters and synthetic regression coverage.

## v1.4 — Accuracy and runtime control

Implemented in the v1.4 line:

- progressive resource routing so agents load only task-relevant instructions;
- validated task-context and resource-plan contracts;
- a project-glossary layer with JSON/CSV validation and scoped
  `PROJECT_APPROVED` enforcement;
- deterministic bilingual QA for protected tokens, placeholders, URLs, paths,
  filenames, CLI/environment tokens, versions, numbers, units, and approved terms;
- semantic worked-example routing without treating examples as evidence;
- bounded content-based format probing and extension/content conflict handling;
- runtime capability probing and format-specific backend selection;
- ingest-coverage validation that separates parser availability from successful or
  complete extraction;
- explicit runtime integration from preflight through QA and repair gates.

## v1.5 — Review Workbench

Implemented in the v1.5 line:

- a local human-in-the-loop bilingual Review Workbench;
- `.dbreview` Review Session contracts for units, issues, evidence, decisions,
  events, anchors, and original-file identity;
- explicit human review states separated from AI suggestions and deterministic QA;
- Portable Review with session-bound decision export/import;
- Export Gate enforcement before native write-back;
- initial DOCX native write-back with original-hash validation, anchor validation,
  non-destructive output, and round-trip verification;
- explicit review-only versus native-export launch modes.

Current working-tree refinements add English/Chinese UI, document upload, multilingual sessions, project glossary upload and scoring, six review-result formats, explained suggestions, responsive panes, theme-aware vector logos, checkpoint DOCX delivery and a post-human Agent review handoff.
These changes are unreleased until a validated release is created.

Further work includes richer alignment, additional native-format adapters and
semantic review integrations. The current handoff does not invoke an LLM.

## Next optional adapters

- TBX terminology interchange adapter;
- TMX translation-memory adapter;
- XLIFF bilingual interchange adapter with inline-code preservation;
- format-specific parser/repair adapters with round-trip fidelity tests;
- richer table, diagram, UI, and embedded-object alignment helpers;
- local evidence cache with provenance and invalidation rules.

## Longer-term workflow tooling

- browser/source retrieval helpers;
- team glossary approval and review workflows;
- project-level evidence and decision history;
- reusable benchmark corpora built only from redistributable or synthetic data.

Future adapters must record provenance and product scope, keep suggestions separate from human decisions, and verify native output through round-trip QA.

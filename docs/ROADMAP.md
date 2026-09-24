# Roadmap

DBabel remains data-light: the repository owns workflow logic, schemas, validators,
adapters, policies, templates, and synthetic tests, not a vendor terminology corpus.

## v1.4 — Accuracy and runtime control

The v1.4 development line adds:

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

## Next optional adapters

- TBX terminology interchange adapter;
- TMX translation-memory adapter;
- XLIFF bilingual interchange adapter with inline-code preservation;
- format-specific parser/repair adapters with round-trip fidelity tests;
- richer table, diagram, UI, and embedded-object alignment helpers;
- local evidence cache with provenance and invalidation rules.

## Longer-term workflow tooling

- browser/source retrieval helpers;
- local desktop/web workbench;
- team glossary approval and review workflows;
- project-level evidence and decision history;
- reusable benchmark corpora built only from redistributable or synthetic data.

Future tooling must preserve DBabel's existing boundaries: no implicit vendor
termbase, no automatic semantic authority from deterministic checks, no silent
cross-product terminology mapping, and no verified-repair claim without round-trip
QA.

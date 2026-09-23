# Changelog

## 1.3.0 — 2026-09-23

- Added installation and invocation instructions for Codex, Claude Code, and other agents, with an accompanying Chinese guide.
- Moved Skill version metadata into standard frontmatter and added Codex display metadata.
- Closed the review workflow with translation, coverage, QA feedback, and final reporting after repair verification.
- Connected findings to source records and added repair outcomes and completion status to the report contract. Version 1.2 reports require migration to the 1.3 schema.
- Added offline report validation, regression tests, synthetic workflow fixtures, and macOS/Linux CI.
- Removed the publishing checklist and refreshed the package manifest.

## 1.2.0
- Prepared the repository for public GitHub release.
- Adopted PolyForm Noncommercial License 1.0.0 for noncommercial use.
- Added `LICENSE`, `NOTICE`, `DISCLAIMER.md`, and explicit license policy.
- Added GitHub upload instructions and repository metadata guidance.
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
- Added GitHub publishing, security, licensing-decision, and third-party notices.

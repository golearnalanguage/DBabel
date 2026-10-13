# Local precheck and translation memory

[中文说明](LOCAL_PRECHECK_AND_MEMORY.zh-CN.md)

DBabel extracts supported document text locally before calling an AI provider. The inspection result reports extracted segments, repeated sources, protected technical literals, possible source typo locations, and exact translation-memory matches. These checks use no API tokens. They do not decide semantic accuracy or approve a translation.

The local translation memory is an indexed SQLite database at `~/Library/Application Support/DBabel/translation-memory.sqlite3` on macOS. A consistent backup is written to `translation-memory.backup.sqlite3` after review changes. It stores human accept/edit/reject decisions by exact source text, language pair and applicability scope. The scope includes `project_id`, vendor, product, version, domain and text role; missing metadata is unknown rather than a wildcard. Set `context.project_id` on aligned units, or use `run_project.py --project-id` for deliberate reuse across documents in one project. Without a project ID, an available original/source SHA-256 supplies a `document:<sha256>` scope.

A later exact approved match in the same scope becomes a **REVIEW** proposal without a provider request; the user must still verify it in context. Rejected targets and linked same-source decisions also stay within that scope. The original `.dbreview` session remains the authoritative review record. When migrating an older database, DBabel first saves `translation-memory.pre-scope-v1.sqlite3`; old rows remain available for management and export as `LEGACY_UNSCOPED`, without automatic reuse or rejection enforcement.

With the optional RapidFuzz integration, the selected unit also shows **Similar approved translations**, including similarity, source differences and scope. These candidates support manual editing and retain `SUGGESTION_ONLY` authority. See [integration dependencies](LOCAL_TOOLING.md#optional-integrations) for installation.

The Terminology view shows the saved memory and an optional cross-vendor database terminology reference list. The reference list is off by default, is not a project-approved glossary, and does not enforce deterministic QA. The project-glossary template can be downloaded from that view; its example starts as `USER_REVIEW`.

Users can edit a stored target, delete an entry, and export the full memory as JSON from the Terminology view. Export contains source, target, language pair, scope, text role, decision and timestamp. Editing a memory entry does not modify the original review decision or approve future segments. Optional [TMX interchange](INTEROPERABILITY_AND_EVIDENCE.md) exports scoped memory or imports unapproved candidates with provenance.

`DBABEL_TRANSLATION_MEMORY`, `DBABEL_GENERAL_TERMS_SETTINGS` and `DBABEL_REJECTION_MEMORY` override the three user-state paths. Run unit tests with `python scripts/run_tests.py` to isolate all three automatically. These files contain user decisions and should be included in user-data backups, never in the packaged app or Git repository.

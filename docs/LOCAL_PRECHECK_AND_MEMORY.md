# Local precheck and translation memory

[中文说明](LOCAL_PRECHECK_AND_MEMORY.zh-CN.md)

DBabel extracts supported document text locally before calling an AI provider. The inspection result reports extracted segments, repeated sources, protected technical literals, possible source typo locations, and exact translation-memory matches. These checks use no API tokens. They do not decide semantic accuracy or approve a translation.

The local translation memory is an indexed SQLite database at `~/Library/Application Support/DBabel/translation-memory.sqlite3` on macOS. A consistent backup is written to `translation-memory.backup.sqlite3` after review changes. It stores human accept/edit/reject decisions by exact source text, language pair, and text role. A later exact approved match becomes a **REVIEW** proposal without a provider request; the user must still verify it in context. A rejected target is excluded. Different source text or text role does not auto-match. The original `.dbreview` session remains the authoritative review record.

The Terminology view shows the saved memory and an optional cross-vendor database terminology reference list. The reference list is off by default, is not a project-approved glossary, and does not enforce deterministic QA. The project-glossary template can be downloaded from that view; its example starts as `USER_REVIEW`.

Users can edit a stored target, delete an entry, and export the full memory as JSON from the Terminology view. Export contains source, target, language pair, text role, decision and timestamp. Editing a memory entry does not modify the original review decision or approve future segments.

`DBABEL_TRANSLATION_MEMORY` and `DBABEL_GENERAL_TERMS_SETTINGS` may override the local paths for isolated tests. These files contain user decisions and should be included in user-data backups, never in the packaged app or Git repository.

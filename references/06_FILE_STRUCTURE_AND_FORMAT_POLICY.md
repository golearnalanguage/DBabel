# File structure and format policy

## Preflight before parsing

Do not infer actual file type from the extension alone. For local reproducible
preflight, use `scripts/detect_document_format.py` and
`scripts/preflight_document.py`.

A format/capability preflight result of `READY` means an eligible backend is
available. It does not prove successful extraction.

If declared extension and content identity conflict, block automatic parser
selection until the mismatch is resolved or explicitly reclassified. Macro-enabled
or legacy containers may require a dedicated workflow.

## Ingest validation

After parsing, verify actual coverage before making full-document claims. Record:

- backend used;
- effective format;
- extracted unit count;
- whether stable locations are available;
- inspected structure classes;
- uninspected structure classes;
- warnings and limitations.

Use `schemas/ingest_report.schema.json` and `scripts/validate_ingest.py` for
machine-readable ingest gates. `PARTIAL` coverage must remain explicit in the final
result.

Terminology decisions depend on text role. Preserve structure and location
identifiers.

## DOCX / DOCM

Distinguish headings, body, tables, captions, headers/footers,
footnotes/endnotes/comments when tooling exposes them. Do not lose run-level
formatting during repair. Macro-enabled DOCM requires macro-aware preservation.

## PPTX / PPTM

Distinguish slide title, body, shapes, grouped shapes, tables, charts, notes, and
master/layout text when accessible. Check overflow after repair. Macro-enabled PPTM
requires a dedicated preservation workflow.

## XLSX / XLSM

Distinguish sheet names, headers, cells, comments/notes, tables, formulas, and
defined structures that are material to the task. Protect formulas and macros unless
explicitly targeted. Do not interpret formula tokens as prose terminology. XLSM
repair requires macro-preserving handling.

## ODF / legacy Office

ODT/ODS/ODP and OLE-based DOC/XLS/PPT require format-aware parsing. If subtype or
preservation capability is not verified, reduce coverage or block generic repair.

## HTML / XML / JSON / CSV

Preserve machine structure. For HTML, distinguish visible text, metadata,
attributes, navigation, UI text, code, scripts/styles. For XML/JSON/CSV, do not
translate keys, delimiters, identifiers, or bound values merely because they look
linguistic.

## Markdown

Use AST-aware handling when available. Protect code fences, inline code, URLs, and
front matter fields unless explicitly targeted.

## TXT

No reliable native document structure; reduce structural confidence while
preserving stable line/span locations when possible.

## PDF

Audit/read-only by default. Preserve page/location references. Editing requires a
dedicated PDF workflow and post-edit validation.

## Image / UI screenshot

Use vision/OCR only to extract candidate text. OCR uncertainty remains uncertainty.
Verify material UI naming against applicable same-version UI/docs.

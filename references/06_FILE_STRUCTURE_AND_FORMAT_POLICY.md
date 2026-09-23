# File structure and format policy

## General
Terminology decisions depend on text role. Preserve structure and location identifiers.

## DOCX
Distinguish headings, body, tables, captions, headers/footers, footnotes/endnotes/comments when tooling exposes them. Do not lose run-level formatting during repair.

## PPTX
Distinguish slide title, body, shapes, grouped shapes, tables, charts, notes, and master/layout text when accessible. Check overflow after repair.

## XLSX/XLSM
Distinguish sheet names, headers, cells, comments/notes, tables. Protect formulas and macros unless explicitly targeted. Do not interpret formula tokens as prose terminology.

## HTML
Use DOM structure. Distinguish visible text, metadata, attributes, navigation, UI text, code, scripts/styles. Preserve markup.

## Markdown
Use AST-aware handling when available. Protect code fences, inline code, URLs, front matter fields unless explicitly targeted.

## TXT
No reliable document structure; reduce structural confidence.

## PDF
Audit/read-only by default. Preserve page/location references. Editing requires a dedicated PDF workflow and post-edit validation.

## Image/UI screenshot
Use vision/OCR only to extract candidate text. Verify UI naming against official same-version UI/docs when material.

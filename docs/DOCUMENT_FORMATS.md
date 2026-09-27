# Document formats

[简体中文](DOCUMENT_FORMATS.zh-CN.md) · [Documentation index](INDEX.md)

DBabel records extraction, review results and original-format delivery separately. The upload panel and `scripts/intake_document.py` share an extractor; `intake.json` records the selected format and omitted structures. Install Python 3.9+ and `requirements-dev.txt` (PyYAML and jsonschema). Limits: 16 MiB per upload, 64 MiB per expanded Office package, 20,000 language/unit pairs per intake.

| Input | Dependency | Extracted scope | Original-format delivery |
|---|---|---|---|
| TXT, `.md` Markdown | Standard library | Non-empty UTF-8 lines and original line numbers | Replace approved lines; preserve BOM, newline sequences, blank lines and untouched bytes. Edited Markdown syntax needs review. Newline insertion is rejected. |
| DOCX | ZIP/XML | Upload: body and table paragraphs. Explicit anchored workflows can include supported text parts. | Patch approved text nodes in a copy. Preserve namespaces, styles, tables, relationships, media and untouched entries. Changed paragraphs with fields, revisions, nested paragraphs, breaks or tabs require separate handling. |
| CSV, TSV | `csv` | Non-empty cells, including headers, with row/column locations | Review results only; no table reconstruction |
| JSON, JSONL | `json` | String values and JSON Pointer locations; keys, numbers and booleans excluded | Review results only |
| HTML | `HTMLParser` | Source-order text outside script/style/template | Review results only; no attributes, CSS layout or dynamic DOM |
| XLSX | Built-in ZIP/XML extractor | Stored text cells, including hidden sheets; pure numbers, dates, booleans and formulas are not sent for translation | Explicit anchored review sessions can write approved cells to a new XLSX. The adapter patches only anchored worksheet-cell XML and verifies untouched OOXML part payloads byte-for-byte. Formula cells are never rewritten. Rich-text runs inside a changed cell are flattened to the approved cell text and require visual review. |
| PPTX | ZIP/XML | Slide paragraphs in XML order | Review results only; notes, charts, SmartArt, masters and image text excluded |
| PDF | Optional `pypdf` | Page text layers | Review results only. Inspect reading order and tables; OCR scans first. No PDF layout reconstruction. |
| XML, DOC/XLS/PPT, macro-enabled Office, ODF, images | Format probe | Recognized; no built-in upload extraction | Convert a copy or supply located units from an appropriate parser |

Install PDF extraction with `python -m pip install pypdf` in the same environment. Text grammars overlap: a TSV may resemble CSV and Markdown may begin with HTML. The extractor confirms text content, then parses the declared grammar; both decisions remain in the intake report.

## Working copies and bilingual results

For one target language, source-only DOCX/TXT/MD intake keeps source text as the current, **unreviewed** working copy. The user or Agent supplies translations; copying source text does not translate or approve it. An existing target document can be the layout template after alignment is confirmed. Multiple target languages use separate review units; create one native session per language for separate native documents.

Every local session, including demos and review-only sessions, exports JSON, CSV, TSV, Markdown, HTML and TXT snapshots. Rows retain language, location and decision/QA status. Pending units retain current text; unaccepted suggestions remain separate. JSON also preserves issues, evidence, notes and revisions. HTML uses responsive side-by-side columns. CSV/TSV prefixes formula-like cells with an apostrophe for spreadsheet text handling.

## Original-format delivery package

For supported anchored sessions, **FINAL** requires the relevant review to be complete; **CHECKPOINT** exports approved changes and leaves pending text unchanged. Each delivery includes the native file, `.receipt.json`, `.handoff.json`, `.handoff.md` and `.bilingual.html`. The browser downloads a ZIP. Handoffs identify changed, unchanged and excluded units, human decisions, notes, revisions, hashes, QA and unperformed Agent review. Existing files are never overwritten; browser exports choose a new numbered name.

DOCX verification compares package parts, non-text XML, and target/non-target text. XLSX verification checks approved-cell round trips, identical ZIP entry sets, byte-identical untouched part payloads, and no worksheet changes outside approved cell elements. It verifies structure and formatting definitions; fonts, application version and translated text length can still change line breaks and pagination. Inspect the copy in Word or LibreOffice. See [implementation assessment](NATIVE_EXPORT_ASSESSMENT.md) and [local walkthrough](WORKFLOW_GUIDE.md).

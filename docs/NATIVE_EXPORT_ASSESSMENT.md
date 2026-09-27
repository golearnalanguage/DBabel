# Native export assessment

[简体中文](NATIVE_EXPORT_ASSESSMENT.zh-CN.md) · [Format matrix](DOCUMENT_FORMATS.md)

To preserve an existing document and replace reviewed text, DBabel edits its package instead of rebuilding extracted paragraphs. Originals remain immutable. Every delivery has a new name and receipt. This implementation adds no third-party document writer.

## Open-source candidates

| Project | Verified license/source | Evaluation |
|---|---|---|
| [python-docx](https://github.com/python-openxml/python-docx) | [MIT](https://github.com/python-openxml/python-docx/blob/master/LICENSE) | Useful Word API. [Paragraph.text](https://python-docx.readthedocs.io/en/latest/api/text.html) assignment replaces runs and removes run formatting; whole-paragraph replacement does not meet this task. No code vendored. |
| [Open XML SDK](https://github.com/dotnet/Open-XML-SDK) | [MIT](https://github.com/dotnet/Open-XML-SDK/blob/main/LICENSE) | Candidate for future .NET Office adaptation and OOXML validation. It does not supply Word's page layout engine. The current bounded writer does not need a second runtime. No code vendored. |
| [Okapi OpenXML Filter](https://okapiframework.org/wiki/index.php/OpenXML_Filter) | Upstream filter documentation consulted; no component selected | Relevant extraction/merge architecture. Integration requires a chosen release, component-license checks and bilingual round-trip fixtures. Not a current dependency or a claim of tested fidelity. |

Assessment date: 2026-09-27. These are architectural evaluations, not benchmarks. Future redistributed components must retain applicable licenses/notices and record versions/dependencies in `THIRD_PARTY_NOTICE.md` and the package inventory.

## Preservation contract

DOCX uses original ZIP entries and namespace-aware XML byte positions. Only selected `w:t` contents and necessary `xml:space` attributes change. Runs, paragraph/table properties, namespace prefixes, comments, relationships and other parts remain. Verification masks permitted text changes and compares remaining XML bytes; untouched parts must match exactly. ZIP compression bytes may differ. Signed/macro-bearing packages and ambiguous or unsupported anchors are rejected. New paragraphs, tabs and manual breaks require a separate writer.

Changes spanning styled runs inherit existing run placement. Review formatting when a new term crosses a bold/italic boundary. Body/table extraction does not imply headers, footnotes or image text were reviewed; intake coverage identifies the scope. Strict OOXML and unsupported encodings need separate adaptation.

TXT/MD replace anchored UTF-8 lines, preserving BOM, mixed newline sequences, empty and untouched lines. Edited Markdown syntax requires review. Bilingual HTML is an additional artifact with its own layout.

## Acceptance and next formats

Tests cover namespaces, styled runs, tables, media, headers, exact replacement, original protection, duplicate text, newlines and checkpoint provenance. Each publication document still needs a Word/LibreOffice visual check. No representative customer file or renderer result establishes identical pagination.

XLSX needs preservation tests for cell types, shared strings, formulas, styles and workbook links. PPTX needs runs, relationships, text-box geometry and overflow tests. PDF needs a separate layout/OCR workflow; text-layer replacement cannot promise editable-source fidelity. These formats export review results until dedicated writers pass those checks.

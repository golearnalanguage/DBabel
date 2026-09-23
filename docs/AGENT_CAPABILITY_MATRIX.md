# Task capabilities

| Task | Required capability | If unavailable |
|---|---|---|
| Lookup from supplied references | Read the source text and relevant context | Request a readable source; preserve unresolved terms |
| Public-source verification | Search and open original pages/documents | Use supplied evidence and mark unresolved findings `REVIEW` |
| DOCX/PPTX audit | Parse paragraphs, tables, slides/shapes and accessible notes | Report inspected text and omitted structures |
| XLSX/XLSM audit | Read cells and distinguish formulas/macros | Inspect only readable content; preserve executable content |
| HTML/Markdown audit | Distinguish prose, markup, code and links | Limit scope to safely identifiable spans |
| PDF/image/UI audit | Page/layout reader or vision/OCR | Report extraction gaps and uncertain labels |
| Bilingual review | Read both documents and align their units | Mark unaligned or missing units for review |
| Translation | Generate target text under terminology constraints | Provide resolved terminology and remaining questions |
| Repair | Format-aware writing to a copy | Return located proposals |
| Repair QA | Reopen output, compare content, render when layout matters | Keep the copy unverified and identify missing checks |
| JSON validation | Python 3.9+ and validation dependencies | State schema validation was not run |

File extensions alone do not prove tool support. Check coverage explicitly,
including notes, comments, charts, embedded objects, and macros when relevant.
A completed review may contain `REVIEW` findings; a verified repair requires passed
round-trip QA. Use the task status defined in `SKILL.md` to make that distinction.

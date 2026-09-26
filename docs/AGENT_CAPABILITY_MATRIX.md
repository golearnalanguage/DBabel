# Task capabilities

| Task | Required capability | If unavailable |
|---|---|---|
| Task/resource routing | Read validated task context and router config | Follow the `SKILL.md` kernel manually and disclose that machine routing was not run |
| File format probe | Bounded byte/container inspection | Do not treat the extension as verified format |
| Parser capability probe | Confirm backend/runtime availability | Do not promise native parsing/writing from package name alone |
| Lookup from supplied references | Read source text and relevant context | Request a readable source; preserve unresolved terms |
| Public-source verification | Search and open original pages/documents | Use supplied evidence and mark unresolved findings `REVIEW` |
| DOCX/PPTX audit | Parse paragraphs/tables/slides/shapes and accessible notes | Report inspected text and omitted structures |
| XLSX/XLSM audit | Read cells and distinguish formulas/macros | Inspect only readable content; preserve executable content |
| HTML/Markdown/structured-text audit | Distinguish prose from markup/code/keys/links | Limit scope to safely identifiable spans |
| PDF/image/UI audit | Page/layout reader or vision/OCR | Report extraction gaps and uncertain labels |
| Ingest validation | Know backend used, extracted structures, gaps, and stable locations | Do not claim full file coverage |
| Bilingual review | Read both sides and align their units | Mark unaligned or missing units for review |
| Project glossary validation | Python 3.9+ plus validation dependencies | Treat glossary structure as unvalidated |
| Deterministic bilingual QA | Aligned bilingual units plus Python 3.9+ | Perform manual QA and state deterministic QA was not run |
| Translation | Generate target text under terminology constraints | Provide resolved terminology and remaining questions |
| Repair | Format-aware writing to a copy | Return located proposals only |
| Repair QA | Reopen output, compare content, render when layout matters | Keep the copy unverified and identify missing checks |
| JSON/schema validation | Python 3.9+ plus validation dependencies | State schema validation was not run |

Format detection, parser availability, successful ingest, and full coverage are four
different claims. Passing one does not establish the next.

File extensions alone do not prove format or tool support. Check coverage explicitly,
including notes, comments, charts, embedded objects, formulas, links, and macros when
relevant.

A completed review may contain `REVIEW` findings; a verified repair requires passed
round-trip QA. Use the task status defined in `SKILL.md` to make that distinction.

## Workbench delivery capabilities

| Task | Implemented behavior | Requirements and limitations |
|---|---|---|
| Native document export | DOCX copy, original hash and target-anchor checks, text round-trip validation | Other formats require a dedicated writer; visual QA is separate |
| Checkpoint export | Apply completed human decisions and list pending IDs in the receipt | Pending text is preserved and listed in the receipt |
| Post-human review | Download source/target, notes, revisions and text hashes for an Agent | Handoff only; semantic review must actually be performed |
| Portable review | Offline decisions, views and report download | Import decisions and run fresh local QA before native export |

| Local Workbench feature | Implemented behavior | Requirements |
|---|---|---|
| Document upload | Text, delimited/structured text and Office extraction with located scope | [Format-specific dependencies and omissions](DOCUMENT_FORMATS.md) |
| Review-result export | JSON, CSV, TSV, Markdown, HTML and TXT in every local session | Pending status stays explicit; native layout is handled separately |
| Multilingual review | One independent unit per source/target-language pair | Agent supplies target-language proposals |
| Glossary upload and score | Canonical CSV/JSON validation and scoped lexical checks | Applicable `PROJECT_APPROVED` entries and explicit languages |
| Interface language | English and Simplified Chinese, including Portable Review | Local browser preference; document content stays verbatim |

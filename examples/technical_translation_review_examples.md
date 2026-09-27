# Technical translation case index

[简体中文](technical_translation_review_examples.zh-CN.md)

The routed diagnostic corpus contains 18 synthetic cases. Original case files are in Simplified Chinese and retain English target examples. The numerical/specification case B3 also has a complete [English version](cases/semantics/B3.md). Cases guide diagnosis; they do not establish facts about a real product. Read the matched case and current evidence rather than the entire corpus.

| Category | Case IDs and mechanism |
|---|---|
| Context | A1 heading/operation mismatch; A2 execution scope; A3 UI object mismatch |
| Semantics | B1 negation and exceptions; B2 prerequisites; B3 numbers, units, scope and scannable specifications; B4 terminology versus technical claims; B5 NULL versus empty string and unknown |
| Product scope | C1 cross-product concepts; C2 version-specific renaming; C3 prose versus exact UI labels |
| Protected content | D1 concept versus identifier/data; D2 ambiguous OCR in executable text; D3 placeholder binding |
| Document structure | E1 PDF reading order/footnotes; E2 merged table headers/formulas; E3 diagram role reversal; E4 HTML translatability and program bindings |

The [Chinese index](technical_translation_review_examples.zh-CN.md) links each original case. `config/example_router.yaml` records exact case paths; `scripts/route_resources.py` returns relevant `example_files`. Keep case IDs stable across languages. Use scoped product evidence, record inspected coverage and preserve human decisions when applying the mechanism to a real review.

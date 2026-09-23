---
name: dbabel-database-terminology-audit
version: 1.2.0
description: Evidence-driven Agent workflow for database-industry terminology lookup, document terminology audit, bilingual review, terminology-aware translation, and safe repair. DBabel ships methodology and constraints, not a terminology database.
---

# DBabel — Database Terminology Audit Agent Skill

## 0. Identity and non-negotiable scope

DBabel is an **Agent workflow and review policy**, not a terminology database, CAT database, vendor glossary mirror, documentation corpus, crawler, or MT engine.

DBabel MUST NOT assume that it owns or ships authoritative terminology data. At runtime it may use, in order of applicability:

1. user-supplied project glossary / approved terminology;
2. user-supplied source documents;
3. authoritative standards and specifications;
4. official vendor/product/version documentation and UI;
5. reputable terminology/reference resources;
6. secondary sources for discovery only when authoritative sources are unavailable.

DBabel defines **how the Agent searches, evaluates, records, adjudicates, and reports terminology evidence**.

### Core principles

1. Concept first, string second.
2. Product context before normalization.
3. Version matters when terminology is version-sensitive.
4. Structure and text role affect terminology decisions.
5. Same-function cross-vendor terms are not automatically synonyms.
6. Search results are discovery aids, not evidence by themselves.
7. No material replacement without adequate evidence.
8. MT/LLM output is never terminology authority.
9. Unknown or conflicting context returns REVIEW, not invented certainty.
10. Protected technical tokens are not polished or translated casually.
11. Terminology verification and technical-claim verification are separate workflows.
12. Original files are read-only by default; requested repairs go to a new copy.
13. DBabel does not distribute vendor terminology datasets or copyrighted documentation corpora.
14. Runtime discoveries do not become globally approved terminology automatically.

## 1. Task modes

Classify every request into one or more modes:

- `LOOKUP` — explain or verify one term or a small term set.
- `AUDIT` — inspect an existing document for terminology issues.
- `BILINGUAL_REVIEW` — compare source and target content.
- `TRANSLATE` — translate content under terminology and protection constraints.
- `REPAIR` — apply approved changes to a copy while preserving structure/layout.
- `SOURCE_RESEARCH` — search authoritative sources for unresolved terminology.
- `CLAIM_ROUTE` — route factual/product-capability claims to separate verification.

`GOVERNANCE` is supported only for a **user-provided/local project glossary**. DBabel itself does not maintain a public approved termbase.

## 2. Mandatory state machine

Execute relevant states in this order. A skipped state must be objectively irrelevant.

```text
INTAKE
  -> PREFLIGHT
  -> INGEST
  -> STRUCTURE
  -> CONTEXT
  -> EXTRACTION
  -> CLASSIFICATION
  -> USER_RESOURCE_RESOLUTION
  -> SOURCE_RESEARCH (when unresolved / conflicted / verification requested)
  -> EVIDENCE_ASSESSMENT
  -> ADJUDICATION
  -> QA
  -> OUTPUT
  -> REPAIR (only when requested and supported)
  -> ROUND_TRIP_QA (after repair)
  -> PROJECT_GLOSSARY_CANDIDATE (only if user wants local governance)
```

Read `references/02_END_TO_END_WORKFLOW.md` for execution details and `config/workflow.yaml` for the machine-readable state contract.

## 3. Preflight

Resolve as many of these as possible before terminology judgment:

- task mode;
- source and target language;
- file format;
- document type and text role;
- database domain/subdomain;
- vendor;
- product/product family;
- product version;
- target audience;
- confidentiality and whether public web research is allowed;
- whether user supplied a glossary, style guide, official manual, UI reference, or prior approved translation;
- whether translation or audit only is requested;
- whether repair is requested;
- whether the original may be modified (default `NO`).

Do not ask for information already inferable from the supplied files, metadata, filename, document context, or current conversation.

## 4. Candidate classes

Every material candidate must be classified before adjudication:

1. `GENERIC_DB`
2. `STANDARD_SQL`
3. `VENDOR_CONCEPT`
4. `PRODUCT_NAME`
5. `UI_LABEL`
6. `SQL_PARAM_IDENTIFIER`
7. `COMMAND_PATH_FILENAME`
8. `ACRONYM`
9. `AMBIGUOUS_HIGH_RISK`
10. optional: `PROTOCOL`, `SECURITY_TERM`, `CLOUD_SERVICE_NAME`, `MARKETING_NAME`, `STANDARD_GENERAL`

Use `references/03_TERMINOLOGY_CLASSIFICATION.md`.

## 5. Protection gate — before translation or replacement

Default to `PROTECT` unless explicit user intent or authoritative product/localization evidence says otherwise:

- official product, service, feature, component names;
- trademarks;
- SQL syntax/keywords when literal syntax must remain executable;
- parameter/configuration keys;
- commands and switches;
- paths and filenames;
- code;
- object identifiers when localization is not explicitly requested;
- URLs;
- version numbers;
- values where textual modification changes runtime behavior;
- formulas/macros;
- exact UI labels when matching a required official UI.

Do not "improve" protected text.

## 6. Scope model

Resolve the narrowest reliable scope:

`document -> section/page/slide/sheet -> table/column/shape -> sentence -> span`

Each material finding should record when determinable:

- domain/subdomain;
- vendor;
- product/product family;
- version;
- source language and target language;
- text role;
- candidate class;
- concept hypothesis;
- scope evidence.

Do not assign one product scope to an entire page/slide when different columns, shapes, or sentences refer to different products.

## 7. Runtime resolution strategy — no bundled terminology database

### 7.1 User resources first

If the user supplies an approved glossary, product manual, style guide, prior approved translation, UI screenshot, or project rules, treat those as scoped project resources. Do not assume they are globally authoritative outside their scope.

Priority within the project:

1. explicit user-approved project rule;
2. same project/product/version approved reference;
3. same vendor/product/version official reference supplied by the user;
4. then external research if allowed and needed.

### 7.2 External research trigger

Search externally when any of the following applies:

- no adequate user-provided resolution exists;
- sources conflict;
- product/version naming needs verification;
- the user explicitly requests verification/source evidence;
- a high-risk ambiguous term would otherwise require guessing;
- a candidate replacement materially changes meaning.

### 7.3 Research sequence

Never jump from raw candidate to replacement. Execute:

```text
candidate
  -> identify concept hypothesis
  -> identify vendor/product/version/domain
  -> choose authoritative source class
  -> formulate minimal search query
  -> discover candidate sources
  -> open original authoritative source
  -> inspect surrounding context
  -> verify product/version/text-role match
  -> capture minimal evidence metadata
  -> compare conflicts/alternatives
  -> adjudicate
```

Search snippets, AI summaries, SEO pages, forums, and blog posts are NOT sufficient final evidence for a material replacement when a primary source should exist.

### 7.4 Query minimization

For public web research, avoid sending confidential sentences. Prefer:

`"candidate term" + vendor + product + version + domain + doc-type keyword`

Examples of doc-type keywords:

- `glossary`
- `reference manual`
- `administrator guide`
- `SQL reference`
- `UI`
- `release notes`
- `terminology`

Use `references/04_SOURCE_AND_EVIDENCE_POLICY.md` and `references/13_SEARCH_AND_RETRIEVAL_STRATEGY.md`.

## 8. Dynamic source hierarchy

There is no universal "Source A always beats Source B" ranking. Match authority to the object being verified.

### Standardized concepts

Applicable standards/specifications -> official standards-body explanatory material -> official vendor implementation docs -> high-quality academic/reference sources.

### Vendor/product terminology

Same vendor + same product + same version official documentation/UI -> same product adjacent version -> vendor glossary/reference -> secondary sources for discovery only.

### UI labels

Same-version official localized UI -> same-version official UI documentation -> adjacent-version official UI/documentation -> REVIEW if unresolved.

### Generic terminology

Applicable standard/specification -> multiple authoritative technical references -> official vendor glossaries/manuals -> reputable terminology resources.

Competitor documentation may help compare concepts but must not rename another vendor's product.

## 9. Evidence record

A material `REPLACE`, `DEPRECATE`, `FORBID`, vendor-specific normalization, or high-risk `KEEP` should carry an evidence record containing as available:

- source title;
- organization/vendor/standards body;
- source type;
- URL/document locator;
- product and version scope;
- publication/update/version date;
- retrieval date;
- minimal supporting passage or exact locator;
- context note;
- authority assessment;
- product/version/context match;
- evidence state: `CURRENT`, `STALE`, `CONFLICTING`, `INSUFFICIENT`.

Do not fabricate citations, URLs, publication dates, versions, pages, excerpts, or UI labels.

If evidence conflicts, preserve the conflict and return `REVIEW` unless scope separation resolves it.

## 10. Decisions

Every material finding must end in exactly one primary decision:

- `KEEP`
- `REPLACE`
- `PROTECT`
- `REVIEW`
- `OUT_OF_SCOPE_CLAIM`

Confidence is separate:

- `HIGH` — direct same-scope authoritative evidence or explicit user-approved project rule.
- `MEDIUM` — strong indirect/adjacent-version evidence; do not auto-repair.
- `LOW` — incomplete/weak evidence.
- `REVIEW_REQUIRED` — critical ambiguity/conflict/missing scope.

Do not invent numeric confidence percentages without a calibrated model.

## 11. Cross-vendor concept discipline

When comparing database products, relations must be explicit and conservative:

- `synonym_of`
- `related_to`
- `product_implementation_of`
- `roughly_corresponds_to`
- `broader_than`
- `narrower_than`
- `not_equivalent_to`

Never silently convert `related_to`, `product_implementation_of`, or `roughly_corresponds_to` into synonymy.

DBabel does not ship a cross-vendor mapping dataset. The Agent constructs a **case-specific mapping from evidence** when the task requires one.

## 12. Structured document handling

Do not flatten structured formats when a structure-aware parser is available.

- DOCX — distinguish headings, body, tables, captions, headers/footers, comments when accessible.
- PPTX — distinguish slide title, body, shape, table, notes, chart labels when accessible.
- XLSX/XLSM — distinguish cells, headers, tables, comments; preserve formulas/macros.
- HTML — DOM-aware; distinguish visible text, attributes, code, navigation/UI.
- Markdown — AST-aware; protect code fences, inline code, URLs.
- TXT — text-only; lower structural confidence.
- PDF — audit/read-only by default; use layout/page structure if available.
- Image/UI screenshot — OCR/vision may discover text, but official UI verification still requires appropriate evidence.

Use `references/06_FILE_STRUCTURE_AND_FORMAT_POLICY.md`.

## 13. Translation mode

Translation is not terminology authority.

Execute:

```text
structure/context analysis
  -> terminology candidate extraction
  -> protection gate
  -> resolve known terms / research unresolved high-risk terms
  -> create HARD and SOFT constraints
  -> MT/LLM pretranslation if available and permitted
  -> terminology validation
  -> context/style refinement
  -> QA
  -> human review when required
```

`HARD` constraints are exact identifiers, official names/UI, protected tokens, or explicit project requirements.

`SOFT` constraints express preferred concept realization while allowing grammar/context variation.

Use `references/07_TRANSLATION_AND_MT_POLICY.md`.

## 14. Technical claim boundary

A sentence can contain correct terminology and still contain a false or unsupported product claim.

Route claims such as performance numbers, compatibility percentages, support matrices, product capabilities, licensing assertions, version availability, benchmark results, or "X is faster/better than Y" to `OUT_OF_SCOPE_CLAIM` unless the current task explicitly includes technical claim verification.

Terminology review may normalize terms inside the claim without endorsing the claim itself.

Use `references/10_TECHNICAL_CLAIM_BOUNDARY.md`.

## 15. Repair gate

Repair only when:

- the user requested/authorized it;
- the output format is supported;
- the decision is sufficiently evidenced;
- protected content remains protected;
- the original is not overwritten unless explicitly requested and safe;
- a new output copy can be validated.

After repair, perform round-trip QA for structure, formulas/macros, links, images, notes, style, page/slide/sheet count, and non-target changes as applicable.

## 16. Project glossary candidates — optional, never global by default

If the user wants a project glossary, DBabel may emit **candidate records**. A runtime Agent must not silently convert a discovered term into a global "approved DBabel term".

Candidate lifecycle is local to the user's project unless the repository owner separately curates a dataset:

`DISCOVERED -> EVIDENCED -> USER_REVIEW -> PROJECT_APPROVED / REJECTED`

The public DBabel Skill repository should contain schemas and examples, not a vendor terminology dataset.

## 17. Required output for lookup/audit

For each material finding, provide:

- location;
- original term/text;
- text role;
- classification;
- vendor/product/version scope when known;
- concept interpretation;
- decision;
- recommendation if any;
- reason;
- confidence;
- source/evidence locator;
- conflicts/alternatives;
- technical-claim flag if relevant.

Do not conceal uncertainty.

Use `schemas/finding.schema.json`, `schemas/evidence.schema.json`, and `references/11_OUTPUT_AND_DATA_CONTRACTS.md`.

## 18. Privacy, copyright, and public repository rule

- Minimize public queries.
- Do not expose customer/internal text when a term-only query suffices.
- Do not upload confidential files to external MT/search systems without authorization.
- Do not republish copyrighted vendor manuals or licensed standards in the DBabel repository.
- Do not ship scraped vendor glossaries as DBabel data unless redistribution rights are clear.
- Store citations/locators and minimal excerpts only as permitted.
- Public examples/tests must use synthetic or clearly reusable content.

Use `references/09_GOVERNANCE_SECURITY_COPYRIGHT.md`.

## 19. Failure behavior

When tools, evidence, file structure, or context are insufficient:

- do not guess;
- preserve protected content;
- mark `REVIEW`;
- state exactly what is missing;
- provide the next best authoritative search target/query;
- never fabricate a successful verification.

## 20. Definition of done

A DBabel task is complete only when:

- relevant scope was resolved or explicitly marked unknown;
- terms were classified before replacement;
- protected tokens were handled;
- authoritative research was performed where required and permitted;
- evidence is traceable;
- cross-vendor distinctions were preserved;
- terminology/technical-claim boundaries were respected;
- QA completed;
- uncertainty is visible;
- repair, if any, passed round-trip QA.

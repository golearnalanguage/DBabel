# Deterministic bilingual QA

Deterministic QA detects mechanically verifiable source/target differences before
or after translation. It complements terminology adjudication; it does not replace
context, evidence, or human/agent review.

## Input contract

The checker consumes aligned bilingual units, not arbitrary DOCX/PPTX/XLSX files.
Document parsing and alignment remain separate responsibilities.

Each unit has a stable `id`, source text, target text, optional location and language
metadata, and optional scope context such as vendor, product, version, domain, and
text role. If alignment is uncertain, mark that condition before deterministic QA;
do not manufacture a 1:1 unit merely to run the checker.

## Output contract

Every emitted item is a `POTENTIAL_ISSUE`. `ERROR` and `WARNING` are policy
severities, not declarations that the translation is factually wrong.

- `ERROR`: a high-confidence integrity rule was violated, such as a missing
  placeholder or project-approved protected literal.
- `WARNING`: the difference is material but may have a legitimate localization or
  contextual explanation, such as a changed number or preferred term.

Deterministic output must not authorize repair by itself. Repair still follows the
DBabel evidence, confidence, authorization, and round-trip QA gates.

## Implemented checks

### High-confidence integrity checks

`PLACEHOLDER_INTEGRITY`
: Compare placeholder identities and counts. Named/indexed placeholders may move
  when their binding remains explicit. Unindexed positional placeholders require
  sequence-sensitive comparison.

`URL_INTEGRITY`
: Flag missing, added, or changed URL literals.

`PATH_INTEGRITY`
: Flag missing, added, or changed Unix, Windows-drive, or UNC path literals.

`FILENAME_INTEGRITY`
: Flag changed file-like literals when they can be identified conservatively.

`CLI_OPTION_INTEGRITY`
: Flag changed command-line options such as `--write-manifest` or `-p`.

`ENV_VAR_INTEGRITY`
: Flag changed environment-variable literals when clearly identified.

`PROTECTED_LITERAL`
: Enforce applicable `PROJECT_APPROVED` glossary entries whose behavior is
  `PROTECT`.

`FORBIDDEN_TERM`
: Flag an applicable `PROJECT_APPROVED` forbidden target designation.

### Review-required difference checks

`VERSION_INTEGRITY`
: Flag changed version-like values. A version change can be intentional, so the
  default severity is `WARNING`.

`NUMBER_INTEGRITY`
: Flag changed simple numeric values. Locale-specific grouping/decimal conventions,
  deliberate unit conversion, dates, identifiers, and version strings can require
  contextual review.

`NUMBER_UNIT_INTEGRITY`
: Bind a simple number to a recognized adjacent unit and flag material pair
  differences. The checker does not automatically treat unit conversion as equivalent.

`PREFERRED_TERM`
: When an applicable approved `TRANSLATE` entry matches the source, flag a target
  that contains neither a preferred nor an admitted designation. This remains a
  warning because grammar and morphology can invalidate naive string expectations.

## Placeholder semantics

The checker must distinguish at least:

- named braces such as `{user}`;
- indexed braces such as `{0}`;
- explicit indexed percent placeholders such as `%1` or `%2$s`;
- unindexed printf-like placeholders such as `%s` and `%d`;
- `${NAME}`-style variable placeholders when treated as inline variables.

Do not collapse every brace pair into a placeholder. Extraction rules must be
narrow, testable, and covered by regression fixtures.

## Number and unit policy

Numbers are not blindly normalized.

Supported comparison behavior:

- compare simple signed integers/decimals when unambiguous;
- keep versions, paths, URLs, placeholders, and identifiers out of number checks
  when they were already classified as another literal type;
- recognize only an explicit, tested technical-unit allowlist;
- do not infer that `1,000.50` and `1 000,50` are equivalent without locale context;
- do not silently convert `500 ms` to `0.5 s` and mark it equal.

These checks report only supported comparisons. Ambiguous locale conventions remain
for contextual review rather than being guessed or reported as certain errors.

## Glossary application

A glossary rule applies only when:

1. its approval state is `PROJECT_APPROVED`;
2. the source term matches according to its declared match mode;
3. source/target language constraints are compatible when supplied;
4. every declared scope field matches the current bilingual unit.

If a required current scope field is absent, skip deterministic enforcement. The
agent may still review the term through the normal DBabel workflow.

## False-positive controls

The checker must:

- exclude literals already consumed by a more specific extractor from broader
  number/filename checks where practical;
- preserve duplicate counts, not just set membership;
- report source and target items used for comparison;
- keep issue IDs stable within one run;
- never rewrite input text;
- never convert a warning into an automatic repair.

## Relationship to localization standards

Localization standards and CAT QA systems distinguish linguistic content from
inline/non-translatable codes and allow automated quality tools to flag potential
issues for review. DBabel follows the same separation: deterministic checks locate
integrity risks, while contextual terminology and translation judgments remain in
the evidence-based workflow.

## Release gate

Before a deterministic checker change is released:

1. add or update synthetic golden cases;
2. test both true-positive and false-positive controls;
3. run the checker against all fixtures;
4. run package/schema/report validation;
5. run existing DBabel regression tests;
6. inspect the diff and regenerate `MANIFEST.sha256`.

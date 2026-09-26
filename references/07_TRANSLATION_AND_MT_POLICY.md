# Translation and MT policy

DBabel is provider-independent. It does not include or require an MT service.

## Workflow

1. validate file ingest/coverage when a file is involved;
2. establish source structure, context, and alignment units;
3. extract terminology candidates;
4. protect non-translatable/executable tokens;
5. resolve user-approved terms within scope;
6. research unresolved high-risk terms if required and permitted;
7. construct terminology constraints;
8. call MT/LLM only if available and authorized;
9. establish aligned source/target units;
10. run deterministic bilingual QA when available;
11. adjudicate any potential issues semantically;
12. refine grammar/style without breaking hard constraints;
13. perform final QA and applicable structural/layout checks.

## HARD constraints

Use for exact project rules, official product names, exact UI labels when required,
identifiers, parameters, commands, placeholders, and other tokens whose alteration
is unacceptable.

## SOFT constraints

Use for preferred domain terminology where inflection, syntax, context, or
stylistic realization may vary.

## Provider behavior

Do not assume a provider's glossary feature guarantees semantic correctness. MT/LLM
output is generated text, not terminology authority. Validate it after translation.

## Deterministic QA checks

The Accuracy Core may detect placeholder, URL, path, filename, CLI option,
environment-variable, version, number/unit, protected-literal, or approved glossary
mismatches. Those results are `POTENTIAL_ISSUE`.

Do not convert a mechanical mismatch directly into `REPLACE`. Re-check alignment,
context, language conventions, scope, and applicable evidence/project rules first.

## Alignment and unresolved terms

Align source and target by content and stable location, not by assuming equal
paragraph/slide counts. Check omissions, additions, numbers, and protected tokens
even when units were merged or split.

Ambiguous alignment is a review condition, not a deterministic QA input.

Preserve unresolved high-risk wording with review notes. If translation produces a
file, reopen it and perform applicable structural/layout checks before delivery.

## Technical translation technique layer

For `BILINGUAL_REVIEW` and `TRANSLATE`, load the
routed technical translation playbook and machine-readable technique registry:

- `references/18_TECHNICAL_TRANSLATION_PLAYBOOK.md`
- `config/translation_techniques.yaml`

Apply them after structural/protected-content identification and scoped terminology
resolution, but before final stylistic polishing. Their priority is:

1. protected technical content;
2. product/version/concept/text-role constraints;
3. propositional and modal fidelity;
4. controlled structural transformations;
5. target-language technical naturalness.

A lower-priority style transformation must not override a higher-priority technical
constraint. Technique examples are diagnostic patterns, not evidence for the current
task.

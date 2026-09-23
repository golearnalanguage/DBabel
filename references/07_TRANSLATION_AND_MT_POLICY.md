# Translation and MT policy

DBabel is provider-independent. It does not include or require an MT service.

## Workflow
1. parse structure/context;
2. extract terminology candidates;
3. protect non-translatable/executable tokens;
4. resolve user-approved terms;
5. research unresolved high-risk terms if permitted;
6. construct terminology constraints;
7. call MT/LLM only if available and authorized;
8. validate terminology after translation;
9. refine grammar/style without breaking hard constraints;
10. perform QA.

## HARD constraints
Use for exact project rules, official product names, exact UI labels when required, identifiers, parameters, commands, and other tokens whose alteration is unacceptable.

## SOFT constraints
Use for preferred domain terminology where inflection, syntax, context, or stylistic realization may vary.

## Provider behavior
Do not assume a provider's glossary feature guarantees semantic correctness. Always validate output after MT.

## Alignment and unresolved terms
Align source and target by content and location. Check omissions, additions,
numbers, and protected tokens even when paragraphs or slides were merged or split.
Preserve unresolved high-risk wording with review notes. If translation produces a
file, reopen it and perform applicable structural/layout checks before delivery;
record those checks under report QA.

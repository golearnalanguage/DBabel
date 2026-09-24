# QA and delivery gates

Run only checks applicable to the routed task and actual available capabilities.
Record unavailable or unrun checks explicitly.

Required checks as applicable:

- ingest/coverage validity for file tasks;
- terminology accuracy and consistency;
- vendor/product/version correctness;
- cross-vendor contamination;
- context/meaning fit;
- acronym/full-form/casing consistency;
- protected-token integrity;
- untranslated residue;
- omission/addition and number/unit integrity;
- evidence coverage and traceability;
- source authority and scope fit;
- technical-claim routing;
- layout/overflow after repair;
- formula/macro/link/image integrity;
- non-target changes;
- output schema validity.

## Deterministic QA gate

Deterministic checks run only on aligned bilingual units. Their output is
`POTENTIAL_ISSUE`; it is not evidence or a semantic decision. A clean deterministic
report does not prove translation correctness, and a flagged mismatch does not by
itself authorize a repair.

## Ingest gate

A parser/backend being available is not equivalent to successful ingest. Full
file-coverage claims require a passed ingest gate for the declared parser scope.
`PARTIAL` ingest requires explicit gaps and normally results in
`COMPLETED_WITH_REVIEW` unless the user explicitly scoped the task to the inspected
subset.

## Repair gate

Repair is permitted only for a located `REPLACE` finding with explicit repair
authorization, HIGH confidence, adequate opened current evidence or an explicit
scoped project rule, no unresolved conflict, and a supported format-aware writing
workflow.

A protected literal requires separate explicit authorization for that literal
change. Confirm that the current source span still matches the recorded original
before writing.

## Round-trip gate

After repair, reopen the output and verify the intended change plus relevant
non-target structure/content. Rendering is required when layout is material.
A successful save is not a passed round-trip gate.

## Delivery outcome

Identify partial coverage and checks that could not run. Failed output QA requires
`FAILED`. An unverified copy must not be described as ready for use.

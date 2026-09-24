# End-to-end workflow

DBabel uses progressive loading. States may be skipped when inapplicable, and the
resource plan is rebuilt when material task state changes.

## INTAKE

Determine requested mode/output, languages, privacy constraints, user resources,
research permission, and repair state. Do not invent missing context.

## TASK_CONTEXT

Record a validated minimal task context. Unknown values remain unknown.

## FORMAT_PROBE

For file input, inspect content signatures/container structure before selecting a
parser. Extension alone is not proof of format. A content/extension conflict blocks
automatic parser selection.

## CAPABILITY_PROBE

Determine which registered backends are actually available. Optional third-party
packages and native/external runtimes are capabilities, not assumptions.

## RESOURCE_ROUTING

Build the resource plan and load only `load_now` plus explicitly routed worked
example sections. Do not load all references as a precaution.

## INGEST

Parse only with an eligible backend. Preserve locations and native structure needed
for the requested task.

## INGEST_VALIDATION

Verify what was actually extracted. Record inspected structures, uninspected
structures, stable-location availability, warnings, and limitations. `READY`
preflight is not ingest success. Partial ingest remains partial coverage.

## STRUCTURE / CONTEXT

Resolve the narrowest reliable scope and text role. Keep uncertainty explicit.

## EXTRACTION / CLASSIFICATION

Extract material candidates and classify them before research or replacement.
Protect executable and non-translatable tokens.

## USER_RESOURCE_RESOLUTION

Use only user-supplied or user-approved resources within their declared scope.
Project approval does not make a wording an official vendor designation.

## SOURCE_RESEARCH

Research unresolved, conflicting, version-sensitive, or explicitly requested items
when permitted. Search discovers sources; open the underlying source before using it
as evidence.

## EVIDENCE_ASSESSMENT / ADJUDICATION

Assess authority, product/version/context fit, recency, and conflicts. Produce one
primary decision and a confidence class. `REVIEW` is a valid outcome.

## TRANSLATION

When requested, translate using resolved HARD/SOFT constraints. Preserve unresolved
high-risk wording with review notes.

## DETERMINISTIC_QA

Only after aligned bilingual units exist, run applicable mechanical checks.
Findings are `POTENTIAL_ISSUE` and return to semantic/context review; they are not
automatic replacement decisions.

## QA

Check terminology, meaning, protected tokens, omissions/additions, numbers, source
residue, evidence coverage, structure, and applicable layout/integrity conditions.

## REPAIR

Only after authorization and repair eligibility. Apply located, high-confidence,
adequately evidenced changes to a copy. Avoid unrelated rewriting.

## ROUND_TRIP_QA

Reopen/parse the repaired output. Verify the intended change and non-target
integrity. Render when layout matters.

## PROJECT_GLOSSARY_CANDIDATE

When governance is requested, route candidates through the project approval
lifecycle; do not auto-approve discovered terms.

## Feedback loops

```text
format/capability blocker -> PREFLIGHT or BLOCKED
ingest gap               -> INGEST / PARTIAL COVERAGE
deterministic issue      -> CONTEXT / ADJUDICATION / QA
terminology QA failure   -> CONTEXT / EVIDENCE_ASSESSMENT
repair QA failure        -> REPAIR or FAILED
state change             -> RESOURCE_ROUTING
```

## OUTPUT

Return findings, coverage, evidence, QA actually performed, repair outcomes,
limitations, and next actions only after every requested operation has a reported
outcome. Use the completion statuses defined in `SKILL.md`.

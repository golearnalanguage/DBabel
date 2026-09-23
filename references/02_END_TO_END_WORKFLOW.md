# End-to-end workflow

## INTAKE / preflight
Determine task mode, languages, format, document role, privacy level, vendor/product/version hints, user-provided glossaries/references, and repair authorization.

## INGEST / structure
Use structure-aware parsing when available. Preserve location identifiers sufficient to report and later repair the exact span.

## CONTEXT
Infer scope from the narrowest reliable unit. Keep uncertainty explicit.

## EXTRACTION
Combine deterministic patterns, user glossary matching, terminology/noun-phrase extraction, and model-assisted discovery. Do not treat every noun as a term.

## CLASSIFICATION
Assign candidate class before research or replacement.

## USER_RESOURCE_RESOLUTION
Use only scoped resources supplied/approved by the user. Record where the rule came from.

## SOURCE_RESEARCH
Research unresolved/high-risk candidates using the authoritative-source policy. Search to find sources; open and read the source before citing it.

## EVIDENCE_ASSESSMENT
Evaluate authority, product match, version match, context match, recency, and conflicts.

## ADJUDICATION
Produce one primary decision and a confidence class. `REVIEW` is a valid successful outcome when evidence is insufficient.

## TRANSLATION
When requested, translate using resolved HARD/SOFT constraints and aligned source units. Preserve unresolved high-risk wording with review notes.

## QA
Check consistency, cross-vendor contamination, abbreviations, casing, protected tokens, residual source-language text, and evidence coverage.

## REPAIR
Only after authorization. Apply approved changes to a copy. Avoid unrelated rewriting.

## ROUND_TRIP_QA
Reopen/parse the repaired file and verify structure and non-target integrity.

## Feedback and OUTPUT
Return terminology QA failures to context/evidence assessment. After repair QA
failure, fix and recheck the copy or mark it FAILED; do not deliver it as verified.
Return final findings, coverage, evidence, QA, repair outcomes, and next actions
only after all requested operations have reached a reported outcome.
Use the completion statuses in `SKILL.md` and the structured output contract.

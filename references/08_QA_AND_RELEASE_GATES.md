# QA and delivery gates

Required checks as applicable:

- terminology accuracy;
- terminology consistency;
- vendor/product/version correctness;
- cross-vendor contamination;
- context/meaning fit;
- acronym/full-form/casing consistency;
- protected-token integrity;
- untranslated residue;
- evidence coverage and traceability;
- source authority and scope fit;
- technical-claim routing;
- layout/overflow after repair;
- formula/macro/link/image integrity;
- non-target changes;
- output schema validity.

## Auto-repair gate
Automatic repair is permitted only for high-confidence, adequately evidenced, non-conflicting changes within a supported format and with explicit repair authorization.

## Delivery outcome
Return the final report after repair and round-trip QA. Identify partial coverage
and checks that could not run. Failed output QA requires FAILED status; an
unverified output must not be described as ready for use.

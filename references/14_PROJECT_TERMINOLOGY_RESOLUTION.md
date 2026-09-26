# Project terminology resolution

This policy defines how DBabel consumes project-local terminology resources without
turning the repository into a terminology database.

## Purpose

A project glossary constrains wording only within its declared scope. It may record
preferred, admitted, or forbidden target terms, or require a literal to remain
unchanged. Project approval is a workflow decision, not proof that a designation is
an official vendor term.

## Authority and scope

Apply resources in this order for the question they actually resolve:

1. explicit user instructions and `PROJECT_APPROVED` project glossary entries,
   within their declared scope;
2. applicable standards for standardized concepts;
3. same-vendor, same-product, same-version official documentation for product
   concepts and official designations;
4. same-version localized UI or product resources for exact UI labels;
5. adjacent-version or secondary sources only with the limitations required by the
   evidence policy.

This is not a single global ranking. Text role matters. A project prose preference
does not override an exact UI label when the task requires the product's actual UI
wording. An official vendor designation does not automatically override a deliberate
project house style unless the current text role requires the official designation.

A glossary entry is applicable only when every non-empty scope field can be matched
to the current unit. Missing current context does not count as a match. Do not widen
vendor, product, version, domain, or text-role scope by inference.

## Canonical entry behavior

DBabel uses the JSON project glossary as the canonical machine-readable form.
CSV is an import/export convenience format and must resolve to the same entry model.

Each entry records:

- a stable `id`;
- source language and source term;
- `behavior`: `TRANSLATE` or `PROTECT`;
- approval state;
- zero or more target designations;
- optional vendor/product/version/domain/text-role scope;
- match behavior;
- notes.

`TRANSLATE` entries may contain target designations with these statuses:

- `PREFERRED`: preferred project wording;
- `ADMITTED`: acceptable alternative;
- `FORBIDDEN`: wording prohibited by an explicit project rule.

`PROTECT` entries preserve the matched source literal. They do not create a target
translation.

Only `PROJECT_APPROVED` entries are enforceable by deterministic QA. Other lifecycle
states remain informational and must not silently become hard constraints:

`DISCOVERED -> EVIDENCED -> USER_REVIEW -> PROJECT_APPROVED / REJECTED`.

## Matching policy

Default matching is conservative:

- exact or token-aware matching only;
- case-sensitive unless the entry explicitly says otherwise;
- Unicode normalization may standardize representation but must not be used to
  invent semantic equivalence;
- substring matching is excluded by default because it creates false
  positives inside identifiers and unrelated words.

For a scoped entry, missing product/version/text-role context makes the entry
inapplicable to that unit. The correct fallback is no deterministic glossary
finding, followed by ordinary DBabel context/evidence analysis if needed.

## Conflict handling

Do not choose by frequency or majority vote.

When applicable project entries conflict:

1. prefer the narrower compatible scope;
2. if equally specific approved entries conflict, emit a conflict/review condition;
3. do not convert the conflict into an automatic replacement;
4. preserve the competing entries and request the missing project decision.

A project preference may govern project wording, but reports must not describe it as
an official vendor designation unless authoritative evidence independently supports
that claim.

## Interchange formats

The internal model is designed to remain mappable to established terminology
concepts, including concept/designation-oriented terminology work and TBX-style
terminology resources. DBabel does not claim full TBX compatibility and does
not import or export arbitrary TBX dialects.

Future TBX/TMX/XLIFF adapters must preserve scope, approval state, text role,
protected literals, and provenance rather than flattening them into an unscoped
two-column term list.

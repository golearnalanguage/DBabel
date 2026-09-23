# DBabel

**Evidence-driven database terminology review workflows for humans and AI agents.**

> Making databases speak the same language — without pretending they use the same words.

DBabel is a public **Agent Skill and methodology package** for database-industry terminology lookup, document auditing, bilingual review, terminology-aware translation, and safe correction.

DBabel does **not** ship a database terminology dataset. It defines how an Agent should identify terminology, resolve vendor/product/version context, search authoritative sources, assess evidence, make review decisions, and report uncertainty.

## What DBabel is

DBabel is a workflow, evidence policy, and review contract. It tells an Agent:

- how to detect terminology candidates;
- how to distinguish generic terminology from vendor/product terminology;
- how to resolve vendor, product, version, and document context;
- when and how to search authoritative sources;
- how to open and verify the original source instead of trusting search snippets;
- how to evaluate conflicting evidence;
- when to `KEEP`, `REPLACE`, `PROTECT`, `REVIEW`, or route a statement to `OUT_OF_SCOPE_CLAIM`;
- how to treat structured files and terminology-aware translation workflows;
- how to separate terminology correctness from technical-claim correctness.

## What DBabel deliberately does not ship

DBabel does **not** include:

- a vendor terminology database;
- a scraped glossary corpus;
- copyrighted vendor manuals;
- licensed standards text;
- a proprietary translation memory;
- a mandatory MT/LLM provider;
- a database server;
- a public "approved terms" dataset.

The Agent obtains terminology evidence at runtime from user-provided resources and authoritative public or authorized sources, following DBabel's research policy.

## Core workflow

```text
Document / term
      ↓
structure + context
      ↓
vendor / product / version / text role
      ↓
candidate classification
      ↓
user-provided project resources (if any)
      ↓
authoritative source research (when required)
      ↓
open original source + inspect context
      ↓
evidence assessment
      ↓
KEEP | REPLACE | PROTECT | REVIEW | OUT_OF_SCOPE_CLAIM
      ↓
QA / optional safe repair
```

## Core principles

1. **Concept first, string second.**
2. **Product context before normalization.**
3. **No material recommendation without traceable evidence.**
4. **Search results discover sources; they are not the source.**
5. **Cross-vendor similarity is not synonymy.**
6. **The public Skill contains rules, not vendor terminology data.**
7. **Unknown or conflicting evidence produces review, not invented certainty.**
8. **Original files are read-only by default; repairs go to a new copy.**

## Repository layout

- `SKILL.md` — normative Agent instructions.
- `references/` — detailed review, source, translation, QA, security, and evidence policies.
- `config/` — machine-readable workflow and search policies.
- `schemas/` — structured output contracts.
- `templates/` — human-readable report templates.
- `examples/` — synthetic usage examples.
- `tests/` — logic/regression cases, not a terminology corpus.
- `docs/` — architecture, research basis, roadmap, licensing, and publishing guidance.
- `.github/` — issue and pull-request templates.

## How to use

Give this repository or folder to an Agent or Skill loader that supports project-level instructions. Load `SKILL.md` as the primary instruction file and expose the supporting files to the Agent.

Typical prompts:

```text
Use DBabel to audit this PPTX for database terminology. Do not rewrite the file.
```

```text
Use DBabel to verify this term. Identify the vendor/product/version scope and cite the authoritative source.
```

```text
Use DBabel to translate this technical manual. Protect commands, parameters, paths, SQL, and product names; research unresolved high-risk terms before translation.
```

## Runtime source model

DBabel does not carry the answers. It carries the method.

At runtime, the Agent should prefer:

1. user-approved project resources;
2. applicable standards and specifications;
3. same-vendor, same-product, same-version official sources;
4. reputable technical and terminology resources;
5. secondary sources only for discovery or clearly qualified fallback.

See `references/04_SOURCE_AND_EVIDENCE_POLICY.md` and `references/13_SEARCH_AND_RETRIEVAL_STRATEGY.md`.

## Project status

**v1.2.0 — public Agent Skill / methodology baseline.**

This release defines the workflow, search strategy, evidence model, file-handling policy, translation constraints, QA, public repository policy, and output schemas. It is not a finished CAT application and does not include a terminology dataset.

## Security and data handling

Do not put confidential customer material, credentials, API keys, internal URLs, proprietary glossaries, translation memories, or non-public documentation into public issues or pull requests. DBabel's research rules are designed to minimize public queries to the smallest terminology context needed.

See `SECURITY.md` and `references/09_GOVERNANCE_SECURITY_COPYRIGHT.md`.

## License

DBabel is licensed for **noncommercial use** under the **PolyForm Noncommercial License 1.0.0**.

You may use, study, modify, and redistribute DBabel for purposes permitted by that license. Commercial use is not granted by this repository.

Official license terms: https://polyformproject.org/licenses/noncommercial/1.0.0

Because commercial use is restricted, DBabel should be described as **source-available / noncommercial**, not as OSI-approved open-source software.

DBabel is provided on an **"AS IS"** basis as described by the license. See `DISCLAIMER.md` for additional project-specific scope notices.

## Third-party material

DBabel may instruct Agents to consult standards bodies and database vendors at runtime, but it does not redistribute their documentation or terminology datasets. Product names and trademarks remain the property of their respective owners. See `THIRD_PARTY_NOTICE.md`.

## Contributing

Contributions to the workflow, source/research policy, schemas, file-handling rules, QA, synthetic examples, and regression tests are welcome subject to the repository license. Do not submit scraped terminology corpora, confidential project material, or copyrighted manuals.

See `CONTRIBUTING.md`.

# DBabel Agent Entry Point

This repository contains the DBabel database terminology audit and
localization methodology.

## Normative instruction

Read and follow `SKILL.md` as the primary normative Agent contract.

Do not treat this repository as a terminology database.

Load supporting files from `references/`, `config/`, `schemas/`,
and `templates/` only when relevant to the current task.

## Required behavior

Before making a material terminology judgment:

1. resolve context;
2. classify the candidate;
3. protect technical tokens;
4. use user-provided scoped resources when available;
5. research authoritative sources when required;
6. open the original source rather than relying on search snippets;
7. preserve uncertainty when evidence is insufficient.

The decision vocabulary is:

- KEEP
- REPLACE
- PROTECT
- REVIEW
- OUT_OF_SCOPE_CLAIM

If repository instructions conflict, `SKILL.md` is authoritative for
DBabel terminology workflow behavior.

## Repository maintenance

For changes to the Skill, schemas, or validation tools, run:

```bash
python scripts/check_package.py
python -m unittest discover -s tests -v
```

Install validation dependencies from `requirements-dev.txt`. After intentional
package edits, regenerate `MANIFEST.sha256` with
`python scripts/check_package.py --write-manifest`, then run the checks again.

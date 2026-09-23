# Contributing to DBabel

DBabel accepts improvements to workflow logic, source/research policy, schemas, file handling, QA, examples, and regression tests.

## Terminology corrections
Do not submit vendor terminology dumps or scraped glossaries.

If an example requires a real term, provide only the minimal evidence necessary and cite the authoritative public source. Prefer synthetic examples for regression tests.

A terminology-related proposal should state:
- candidate term;
- vendor/product/version scope;
- context/text role;
- proposed rule change (if any);
- authoritative source locator;
- why this changes the Skill method rather than merely adding a data record.

## Pull requests
Keep methodology changes separate from any optional dataset work. DBabel core must remain usable without a terminology database.

## Validate changes

Install `requirements-dev.txt` in a virtual environment. Run
`python scripts/check_package.py` and `python -m unittest discover -s tests -v`.
After intentional edits, regenerate checksums with
`python scripts/check_package.py --write-manifest` and re-run validation.
For workflow changes, also exercise a relevant case from
[behavioral evaluation](tests/BEHAVIORAL_EVAL.md) and record the observed result.

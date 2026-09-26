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

## Documentation changes

Write around the current DBabel task and observed behavior. Distinguish implemented capabilities, optional runtime support, unreleased changes and future work. Keep historical release notes factual. Avoid duplicating installation, export and evidence rules across documents; link to their owning guide. Use `FINAL` and `CHECKPOINT` consistently and distinguish deterministic QA, Agent suggestions and human approval.

Keep each diagnostic case in its own category file and update the example router. Run `python scripts/check_documentation.py` and relevant functional regressions when changing workflows.

## Browser interaction regression

`tests/workbench_browser_smoke.cjs` exercises desktop and portable decisions, themes, filters, notes, QA and downloads using Playwright. Use a temporary copy of the synthetic demo bundle: the test changes its decisions. Build a portable HTML from that copy, start a local workbench for the copy, then supply `DBABEL_TEST_URL` (including its session token) and `DBABEL_TEST_PORTABLE` (absolute file path). Run `node tests/workbench_browser_smoke.cjs` in an environment with Playwright available. `DBABEL_CHROME` optionally selects an installed browser executable. Playwright is not a core runtime dependency.

The additional `tests/workbench_exchange_smoke.cjs` covers interface language, theme, responsive layouts at four widths, six result downloads, glossary upload, preflight and multilingual intake. It creates a new session and rotates the server token; run it after the existing desktop/portable smoke test. Set `DBABEL_TEST_OUTPUT` to a scratch directory for downloads and screenshots. Never point these tests at a user's active review session.

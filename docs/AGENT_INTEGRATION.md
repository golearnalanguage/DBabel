# Agent integration

Clone the complete repository as a skill folder named
`dbabel-database-terminology-audit` and keep the relative directory structure
intact.

`SKILL.md` is intentionally a small runtime kernel. Supporting references are loaded
progressively through `config/resource_router.yaml`; do not preload the entire
`references/` directory.

The [README](../README.md#how-to-use) contains installation and invocation prompts.

## Runtime sequence

For a text-only task, establish a task context and route resources directly.

For a file task:

1. probe content format rather than trusting the extension;
2. check parser/backend capability;
3. build the initial task context and minimal resource plan;
4. load only `load_now`;
5. ingest with the selected/declared capability;
6. validate actual ingest coverage;
7. continue the routed terminology/translation workflow;
8. re-route whenever material state changes.

A reproducible local preflight can be generated with:

```bash
python scripts/prepare_runtime.py \
  --mode AUDIT \
  --file path/to/document.docx \
  --declare-backend native_agent \
  --output runtime-plan.json
```

The resulting `READY_FOR_INGEST` state is not a statement that ingestion succeeded.

After parsing, a machine-readable ingest report can be validated with:

```bash
python scripts/validate_ingest.py ingest-report.json
```

See [runtime preflight and ingest validation](../references/17_RUNTIME_PREFLIGHT_AND_INGEST_VALIDATION.md).

## Evidence and outputs

Text-only lookup can run from supplied references. Public-source verification needs
search plus opening the original source. Native document repair additionally needs
a format-aware writer and applicable round-trip QA.

Check the [capability matrix](AGENT_CAPABILITY_MATRIX.md) and the
[format backend registry](../plugins/FORMAT_BACKENDS.md) before promising a native
file result.

Deterministic bilingual QA is optional tooling for already aligned units. It cannot
replace semantic review or evidence assessment.

## Technique candidate routing

When the agent has already identified explicit translation signals for aligned or translatable units, it may route those signals against the Technical Translation Playbook catalog with `scripts/suggest_translation_techniques.py`.

The router performs exact trigger matching and filters by task mode and concrete text role. It does not inspect raw source text, perform fuzzy semantic matching, or turn a signal into a finding. Unmatched signals remain visible in the candidate report.

Candidate output guides semantic adjudication only. A candidate does not authorize `KEEP`, `REPLACE`, `PROTECT`, `REVIEW`, repair, or human approval. Only an adjudicated semantic finding may carry formal `technique` metadata.

For structured DBabel reports, load `schemas/audit_report.schema.json` and its local
references. Run `scripts/validate_report.py` with dependencies from
`requirements-dev.txt` when Python is available. The validator checks recorded
contract consistency; it does not verify source truth or file integrity.

## Local updates

For a Git-based installation, run `git -C <installed-skill-folder> pull --ff-only`.
Preserve local edits before updating. Keep one installed copy per host to avoid
duplicate skill entries.

## Installation references

- [Codex local skill locations and discovery](https://learn.chatgpt.com/docs/build-skills)
- [Claude Code skills and invocation](https://code.claude.com/docs/en/skills)
- [Anthropic skill examples](https://github.com/anthropics/skills)

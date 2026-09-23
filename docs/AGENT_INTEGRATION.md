# Agent integration

Clone the complete repository as a skill folder named
`dbabel-database-terminology-audit`. Keep the relative directory structure intact:
`SKILL.md` loads references, worked examples, configuration, schemas, and
templates as needed.
The [README](../README.md#how-to-use) contains installation and invocation prompts.

For a repository checkout, `AGENTS.md` directs terminology tasks to `SKILL.md`.
Other maintenance tasks use the repository's validation commands. A standalone
skill loader discovers the YAML `name` and `description` in `SKILL.md`;
`agents/openai.yaml` supplies the Codex display name and default prompt.

A task should supply the input file or text, desired mode/output, and any available
product/version context and approved references. Infer missing context when
possible; ask only when it changes the decision.

## Evidence and outputs

Text-only lookup can run from supplied references. Public-source verification
needs search and source reading. Native document repair additionally needs a
format-aware writer and suitable QA tools. Check the
[capability matrix](AGENT_CAPABILITY_MATRIX.md) before promising a file output.

For structured reports, load `schemas/audit_report.schema.json` and its local
references. Run `scripts/validate_report.py` with the dependencies in
`requirements-dev.txt` if Python is available. Report generation itself does not
require Python. The validator does not fetch sources or edit documents.

## Local updates

For a Git-based installation, run `git -C <installed-skill-folder> pull --ff-only`.
Preserve any local edits before updating. Keep one installed copy per host to
avoid duplicate skill entries.

## Installation references

- [Codex local skill locations and discovery](https://learn.chatgpt.com/docs/build-skills)
- [Claude Code skills and invocation](https://code.claude.com/docs/en/skills)
- [Anthropic skill examples](https://github.com/anthropics/skills)

<p align="center">
  <img src="assets/dbabel-social-preview.png"
       alt="DBabel — Database terminology review for AI agents."
       width="100%">
</p>

# DBabel

**Database terminology review for AI agents.**

DBabel helps translators, technical writers, and database teams use the right term
for the right product, version, and context. Its name combines **DB** (Database)
with **Babel** (the Tower of Babel), reflecting the work of connecting languages.

Use it to check a term, review a document or translation, translate with consistent
terminology, or produce a corrected copy. Each material change is tied to its
location and supporting evidence, so you can see what changed and why.

[中文说明](README.zh-CN.md) · [Skill instructions](SKILL.md) · [Examples](examples/)

## How to use

### Codex

Ask Codex to install the complete skill folder:

```text
Install DBabel as a local Codex skill by cloning the complete repository:
https://github.com/golearnalanguage/DBabel
Destination: ~/.agents/skills/dbabel-database-terminology-audit
The entry point is SKILL.md at the repository root.
Keep all supporting directories alongside it.
```

Once the skill appears in the skill picker, attach your document or provide its
local path, then invoke it:

```text
$dbabel-database-terminology-audit Review the attached database manual's
English terminology. Use the product and version stated in the manual.
Return the location, suggested wording, reason, and source for each issue.
```

If it does not appear, start a new session or restart Codex. For manual installation
on macOS/Linux:

```bash
mkdir -p "$HOME/.agents/skills"
git clone https://github.com/golearnalanguage/DBabel.git \
  "$HOME/.agents/skills/dbabel-database-terminology-audit"
```

Both methods use the same folder; you only need to install once.

### Claude Code

Run in a terminal:

```bash
mkdir -p "$HOME/.claude/skills"
git clone https://github.com/golearnalanguage/DBabel.git \
  "$HOME/.claude/skills/dbabel-database-terminology-audit"
```

Then invoke it in Claude Code, replacing the example path with your document:

```text
/dbabel-database-terminology-audit Review ./docs/database-manual.md for database terminology. Report each issue with its location, reason, and source.
```

### Other agents

For an agent that can read GitHub files, paste this prompt and attach your document:

```text
Use DBabel from https://github.com/golearnalanguage/DBabel to review the
attached document's database terminology.

First read https://raw.githubusercontent.com/golearnalanguage/DBabel/main/SKILL.md.
Load the supporting files it references from the same repository as needed.
Identify the product/version context, verify material changes against appropriate
sources, and return located findings with evidence and unresolved questions.
```

For a local-only agent, download the [repository ZIP](https://github.com/golearnalanguage/DBabel/archive/refs/heads/main.zip),
extract it, and give the agent the extracted folder and your document:

```text
Read ./DBabel-main/SKILL.md and use its supporting files to review
./docs/database-manual.md. Use the supplied glossary and manuals as evidence.
Return located findings and identify terms that need further verification.
```

Replace these paths with the actual extracted folder and input document.

## Common tasks

After installing in Codex, use one of these prompts. In Claude Code, replace the
leading `$` with `/`.

**Check a term**

```text
$dbabel-database-terminology-audit Check whether “schema” is used correctly
in this PostgreSQL 17 paragraph: [paste paragraph]. Explain the concept and cite
the relevant official documentation.
```

**Review a translation**

```text
$dbabel-database-terminology-audit Compare the attached Chinese source and
English translation. Check database terms, product names, abbreviations, and
technical tokens. Report source/target locations and suggested corrections.
```

**Translate and verify**

```text
$dbabel-database-terminology-audit Translate ./docs/manual-zh.md into English
using ./docs/project-glossary.csv. Preserve SQL, configuration keys, paths, and
product names. Save a new file and report terminology that still needs review.
```

**Repair a document**

```text
$dbabel-database-terminology-audit Review ./docs/database-manual.md and apply
well-supported terminology corrections to a new copy. Reopen the result, check
protected tokens and non-target content, and return the file and change log.
```

## How review works

Context → classification → source reading → evidence assessment → decision → QA
→ requested repair and recheck → final report.

| Decision | Result |
|---|---|
| `KEEP` | Keep the wording in this context |
| `REPLACE` | Recommend a specific, evidenced correction |
| `PROTECT` | Preserve an exact name or technical token |
| `REVIEW` | Identify the evidence or context still needed |
| `OUT_OF_SCOPE_CLAIM` | Route a factual claim for separate verification |

DBabel uses your approved references and authoritative sources retrieved during
the task. Document coverage and repair support depend on the agent's tools.
See [agent integration](docs/AGENT_INTEGRATION.md) and
[capabilities](docs/AGENT_CAPABILITY_MATRIX.md).

## Validation

Repository version: **1.3.0**. See [changes](CHANGELOG.md) and
[report format](references/11_OUTPUT_AND_DATA_CONTRACTS.md).

To check the package and report contracts locally (Python 3.9+):

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python scripts/check_package.py
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/validate_report.py examples/audit_report.json
```

These checks cover schema validity, evidence references, repair gates, and package
integrity. The agent still needs to read sources and inspect document output.
See [behavioral evaluation](tests/BEHAVIORAL_EVAL.md) for end-to-end cases.

## License and contributions

DBabel is available under the [PolyForm Noncommercial License 1.0.0](LICENSE).
See [contributing](CONTRIBUTING.md) for workflow, schema, and test improvements.

Installation conventions follow the official [Codex skill guide](https://learn.chatgpt.com/docs/build-skills)
and [Claude Code skill guide](https://code.claude.com/docs/en/skills).

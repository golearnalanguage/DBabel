<p align="center">
  <img src="assets/dbabel-social-preview.png"
       alt="DBabel — Database terminology review for AI agents."
       width="100%">
</p>

# DBabel

<p align="center">
  <a href="https://github.com/golearnalanguage/DBabel/actions/workflows/validate.yml"><img alt="Validate DBabel" src="https://img.shields.io/github/actions/workflow/status/golearnalanguage/DBabel/validate.yml?branch=main&amp;label=Validate%20DBabel&amp;logo=github"></a>
  <a href="https://github.com/golearnalanguage/DBabel/releases"><img alt="Release" src="https://img.shields.io/github/v/release/golearnalanguage/DBabel?display_name=tag&sort=semver"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-PolyForm%20Noncommercial%201.0.0-blue"></a>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.9%20%7C%203.11-3776AB?logo=python&logoColor=white">
</p>

**Database terminology review and bilingual quality checks for AI agents.**

DBabel helps reviewers check technical translations against the right product, version and context. An Agent prepares located findings, evidence and suggested wording; a human reviews the changes in a local workbench. Reviewed DOCX copies are exported with integrity checks and an audit receipt.

DBabel provides the workflow and tools. You supply the documents, project glossary and approved reference material. It does not bundle a vendor terminology database or run a translation model by itself.

[中文说明](README.zh-CN.md) · [Workflow guide](docs/WORKFLOW_GUIDE.zh-CN.md) · [Agent entry point](SKILL.md) · [Case index](examples/technical_translation_review_examples.zh-CN.md)

<p align="center"><img src="assets/platform-support.svg" alt="macOS, Windows and Linux; Python 3.9 or later" width="640"></p>

## Review Workbench

<p align="center"><img src="assets/dbabel-review-workbench-preview.png" alt="DBabel review workspace with aligned text, evidence and human decisions" width="100%"></p>

Read the source and target side by side, inspect the supporting evidence, then **Accept Suggestion**, **Keep Current**, **Edit**, **Defer**, **Block**, or **Waive**. AI suggestions, potential issues and human decisions remain separate.

- **Focus the review:** filter by status, issue type, location or tag. Select a page or all matching segments for an explicit bulk Keep Current / Defer decision.
- **Deliver in stages:** Checkpoint export applies reviewed changes and keeps pending content unchanged. Its receipt lists the unreviewed scope. Final export requires the full review gate.
- **Check human edits:** download an Agent handoff from Reports to check typos, mistaken wording and omissions. Suggestions return to human review; downloading the report does not run an LLM.
- **Review offline:** a self-contained Portable Review file exports decisions for import into the matching local session and fresh QA.

Native write-back currently supports **DOCX**. Other inputs can be reviewed within available parser coverage; format recognition alone does not imply native export support.

## Workflow

| Step | Action | Next handoff |
|---|---|---|
| Prepare | Declare task scope, languages, resources and permission to repair | Task context and resource plan |
| Ingest | Check the real format, parser capability, extracted coverage and alignment | Located source/target units |
| Diagnose | Run applicable integrity checks, assess semantics and inspect evidence | Findings and suggested wording |
| Review | Record explicit human decisions in the Workbench | Reviewed targets and pending scope |
| Recheck | Review human edits for spelling and word misuse, then rerun QA | New suggestions for human confirmation |
| Deliver | Export a checkpoint or final DOCX copy and verify the result | Output and export receipt |

Load only resources needed for the current step. The [18 worked cases](examples/technical_translation_review_examples.zh-CN.md) are split into individual files across five problem categories. The router returns exact `example_files`; examples are diagnostic patterns, never evidence for the current document.

## Start a local review

Python 3.9+:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python scripts/start_review_workbench.py examples/review_workbench_demo.dbreview
```

The demo is review-only. For a real session, prepare aligned units with `scripts/create_review_session.py` and start the workbench with `--original target.docx --output reviewed.docx` to enable native export. See [Review Workbench](docs/REVIEW_WORKBENCH.md) for session creation, portable review and export details.

## Use with an Agent

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

### Claude Code

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
Follow its progressive-loading workflow: build the task context, preflight files
when applicable, route only the required resources, and avoid loading every
reference file by default. Return located findings with evidence, coverage, QA
actually performed, and unresolved questions.
```

For a local-only agent, download the [repository ZIP](https://github.com/golearnalanguage/DBabel/archive/refs/heads/main.zip),
extract it, and provide the complete folder together with your document and approved
references.

## Scope and guarantees

- Check terminology, bilingual meaning, protected tokens and scoped project wording. Database administration and SQL debugging are outside this workflow.
- Deterministic QA checks placeholders, paths, URLs, numbers, units and other literal content. A `POTENTIAL_ISSUE` requires interpretation; a passing check is not semantic approval.
- Preserve product/version distinctions and uncertainty. Evidence must support the actual claim and scope.
- Native export checks the original hash, changed text anchors and round-trip text integrity. It writes a new copy and preserves non-target text. Visual layout review remains a separate check.
- Agent reports disclose inspected scope, unresolved items and unavailable checks. DBabel does not claim TBX, TMX or XLIFF compatibility.

## Development and reference

Repository version: **1.5.0**. Review Workbench version: **1.5.0**. This working tree also contains unreleased refinements recorded in [Changes](CHANGELOG.md).

```bash
python -m py_compile scripts/*.py
python -m unittest discover -s tests -v
python scripts/check_package.py
```

After intentional package edits, regenerate `MANIFEST.sha256` with `python scripts/check_package.py --write-manifest`, rerun validation and check `git diff --check`.

[Architecture](docs/ARCHITECTURE.md) · [Local tools](docs/LOCAL_TOOLING.md) · [Capabilities](docs/AGENT_CAPABILITY_MATRIX.md) · [Post-review QA](docs/POST_REVIEW_QA.md) · [Package index](PACKAGE_INDEX.md) · [License](LICENSE)

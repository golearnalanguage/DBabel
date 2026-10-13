# Agent integration

[简体中文](AGENT_INTEGRATION.zh-CN.md) · [Documentation index](INDEX.md)

Clone the complete repository as a skill folder named
`dbabel-database-terminology-audit` and keep the relative directory structure
intact.

`SKILL.md` defines task selection, naming, output contracts and the review workflow. Supporting references are loaded
progressively through `config/resource_router.yaml`; do not preload the entire
`references/` directory.

The [README](../README.md#use-with-an-agent) contains installation and invocation prompts.

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

`READY_FOR_INGEST` starts extraction. Record the extracted structures and gaps after the parser runs.

After parsing, a machine-readable ingest report can be validated with:

```bash
python scripts/validate_ingest.py ingest-report.json
```

See [runtime preflight and ingest validation](../references/17_RUNTIME_PREFLIGHT_AND_INGEST_VALIDATION.md).

## Translation runtime, scope and recovery

Preserve `context.project_id`, vendor, product, version, domain and each unit's concrete text role when preparing aligned data. An explicit stable project ID enables deliberate reuse across its documents; when no project ID is supplied, an available original/source SHA-256 defines a document scope. Missing metadata is unknown. Exact memory, rejection constraints, similar-memory candidates and linked same-source human decisions use the same scope. Older unscoped memory stays available for management/export without automatic enforcement. See [local memory](LOCAL_PRECHECK_AND_MEMORY.md).

For the provider-backed runtime, install the optional dependencies described in [local tooling](LOCAL_TOOLING.md#optional-integrations), then run:

```bash
python scripts/check_provider_connection.py --provider-config provider.json --task-check
python scripts/run_project.py manual.docx --source-language zh-CN --target-language en --text-role PROSE --provider-config provider.json --project-id my-manual --workspace-root output/runtime
python scripts/list_resumable_runs.py --workspace-root output/runtime
```

`--task-check` verifies one synthetic translation contract and protected-literal preservation. `TASK_READY` reports that sample passed; evaluate the actual document through ingest, QA and review. Provider configuration may select `transport_backend` as `auto`, `stdlib` or `sdk`; DBabel retains one bounded retry owner with either client.

Resume with the original command plus `--resume-run output/runtime/RUN_<id>`. Preserve source, languages, provider identity and memory context. Discovery includes failed/interrupted runs and inactive unfinished stages, with an OS-held lock preventing concurrent writers. Resume rechecks identities and saved artifacts, reusing completed batches rather than inventing completion states.

## Evidence and outputs

Text-only lookup can run from supplied references. Public-source verification needs
search plus opening the original source. Native document repair additionally needs
a format-aware writer and applicable round-trip QA.

Optional [TMX interchange and evidence-cache commands](INTEROPERABILITY_AND_EVIDENCE.md) retain scope and provenance. Imports produce unapproved candidates; cache checks identify expired or changed sources and affected units while preserving human decisions. Reopen sources and repeat applicable review/QA before relying on stale evidence.

Check the [capability matrix](AGENT_CAPABILITY_MATRIX.md) and the
[format backend registry](../plugins/FORMAT_BACKENDS.md) before promising a native
file result.

Deterministic bilingual QA is optional tooling for already aligned units. It cannot
replace semantic review or evidence assessment.

## Technique candidate routing

When the agent has already identified explicit translation signals for aligned or translatable units, it may route those signals against the Technical Translation Playbook catalog with `scripts/suggest_translation_techniques.py`.

The router performs exact trigger matching and filters by task mode and concrete text role. It does not inspect raw source text, perform fuzzy semantic matching, or turn a signal into a finding. Unmatched signals remain visible in the candidate report.

Candidate output guides semantic adjudication only. A candidate does not authorize `KEEP`, `REPLACE`, `PROTECT`, `REVIEW`, repair, or human approval. Only an adjudicated semantic finding may carry formal `technique` metadata.

For aligned bilingual units, `scripts/extract_translation_signals.py` can create candidate-routing observations from an explicit allowlist of surface-detectable cues. Each generated signal records its side, detector ID, matched text, and span when available. Language-aware lexical rules are skipped rather than guessed when language metadata is missing. Semantic-only playbook triggers remain outside this deterministic extractor and require agent adjudication.

For an integrated machine handoff, `scripts/build_translation_review_intake.py` composes surface observations, source/target signal contrasts, technique candidates, and deterministic QA. In TRANSLATE mode with empty targets it produces a PRE_TRANSLATION intake and waits for target text before bilingual QA. Once targets exist, or in BILINGUAL_REVIEW mode, the intake terminates at semantic adjudication rather than creating findings automatically.

For structured DBabel reports, load `schemas/audit_report.schema.json` and its local
references. Run `scripts/validate_report.py` with dependencies from
`requirements-dev.txt` when Python is available. The validator checks recorded
contract consistency. Verify external evidence by opening its source and document integrity by reopening the output.

## Local updates

For a Git-based installation, run `git -C <installed-skill-folder> pull --ff-only`.
Preserve local edits before updating. Keep one installed copy per host to avoid
duplicate skill entries.

## Installation references

- [Codex local skill locations and discovery](https://learn.chatgpt.com/docs/build-skills)
- [Claude Code skills and invocation](https://code.claude.com/docs/en/skills)
- [Anthropic skill examples](https://github.com/anthropics/skills)

## Human review handoff

For approval-required changes, create a `.dbreview` session and use the [Workbench](REVIEW_WORKBENCH.md). After human edits, generate a revision-bound handoff with `scripts/build_post_review_report.py` and follow [post-review QA](POST_REVIEW_QA.md). Do not import Agent suggestions as human decisions. Route accepted edits through another review and QA cycle. `CHECKPOINT` exports reviewed changes with explicit pending scope; `FINAL` keeps the full gate.

## Suggested-unit contract and multilingual naming

Name a single-language session `manual.en.dbreview` and a multilingual session `manual.multilingual.dbreview`. Use a stable unit ID per source/target-language pair. Input to `create_review_session.py` uses `target` for the current text and optional `suggested_target` plus `suggestion_reason` for the proposal:

```json
{"id":"U00001_en","location":"line:1","source_language":"zh-CN","target_language":"en","text_role":"PROSE","context":{"project_id":"my-manual","product":"MyDatabase","version":"1.0"},"source":"主库发送归档日志。","target":"","suggested_target":"The primary database sends archived logs.","suggestion_reason":"Preserve the primary database as the actor; use the project-approved designation."}
```

Provide substantive guidance for every unit. Preserve current decisions when returning to a session: create a new proposal session or give revision-bound suggestions to the reviewer. Do not replace the session's decision file with Agent-authored acceptance states.

`intake_document.py` prepares located source units for one or multiple target languages. `export_review_results.py` emits status-bearing review documents in six formats. See [document formats](DOCUMENT_FORMATS.md) and [the Chinese walkthrough](WORKFLOW_GUIDE.zh-CN.md).

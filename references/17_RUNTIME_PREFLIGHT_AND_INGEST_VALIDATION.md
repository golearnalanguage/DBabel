# Runtime preflight and ingest validation

This reference governs the boundary between a user-supplied file and DBabel's
terminology/translation workflow.

## Why the boundary exists

Four claims must remain separate:

1. the filename claims a format;
2. content probing identifies a format;
3. a parser/backend is available;
4. the parser actually extracted the structures required by the task.

Passing an earlier claim does not prove a later one.

## Bounded format preflight

Use content signatures and bounded container metadata. Do not execute macros,
scripts, embedded objects, or document code during format detection. Do not unpack
an archive merely to identify it.

A declared extension/content conflict blocks automatic parser selection.

Macro-enabled OOXML, legacy Office containers, generic archives, and formats without
a verified repair backend may require a dedicated workflow.

## Capability preflight

A package import is not always sufficient proof of usable capability. Backends that
depend on external/native runtimes must remain unavailable until that runtime is
verified or explicitly declared by the hosting agent.

`native_agent` is never inferred by the local script; the hosting runtime must
declare it when applicable.

## Runtime preparation

For reproducible local setup:

```bash
python scripts/prepare_runtime.py \
  --mode AUDIT \
  --file manual.docx \
  --declare-backend native_agent \
  --output runtime-plan.json
```

The command combines:

- format/capability preflight;
- validated task-context construction;
- progressive resource routing.

`READY_FOR_INGEST` authorizes only the next processing step. It is not an ingest
coverage result.

## Ingest report

After parsing, record a report with:

- source;
- effective format;
- backend used;
- status: `PASS`, `PARTIAL`, or `FAIL`;
- extracted unit count;
- stable-location availability;
- structure coverage;
- warnings and limitations.

Validate it with:

```bash
python scripts/validate_ingest.py ingest-report.json
```

### PASS

`PASS` requires stable locations and no uninspected structures within the declared
parser scope. Structure status must be `VERIFIED` or `NOT_APPLICABLE`.

### PARTIAL

`PARTIAL` is usable only when gaps or limitations are explicit. It does not support
a claim of full-document coverage.

### FAIL

`FAIL` means the attempted ingest cannot support the requested file-level work.
State the blocker and use `BLOCKED` or retry with another valid parser/workflow.

## State transition

```text
file
  -> format probe
  -> capability probe
  -> resource route
  -> parser ingest
  -> ingest validation
       | PASS    -> task workflow
       | PARTIAL -> task workflow with explicit coverage gaps
       | FAIL    -> retry or BLOCKED
```

If the parser/backend changes, regenerate or reassess the ingest report because
coverage properties may change.

Do not use a clean deterministic bilingual QA report to compensate for missing file
coverage. Deterministic QA operates only on the aligned units it was given.

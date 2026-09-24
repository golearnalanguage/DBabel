# Progressive resource routing

DBabel uses progressive loading so an agent reads only the instructions required by
the current task. The router is a control plane, not a source of technical truth.

## Runtime sequence

1. Load the `SKILL.md` kernel and `config/resource_router.yaml`.
2. For file input, run format/capability preflight before parser selection.
3. Create a validated task context. `scripts/prepare_runtime.py` can combine file
   preflight, task-context creation, and initial routing.
4. Route input, mode, format, project-resource, risk, research, QA, and repair resources.
5. Load only `load_now`.
6. Load only the worked-example sections listed in `example_sections`; examples are
   diagnostic patterns, never evidence.
7. After parsing a file, validate actual ingest coverage; preflight `READY` is not
   ingest success.
8. Re-route if the task state materially changes, such as repair authorization,
   newly available aligned bilingual units, or an unresolved term requiring research.
9. Run task-specific work and QA, then report unrun or unavailable checks explicitly.

Do not pre-load every reference file as a precaution. A full reference sweep defeats
the routing model, consumes context, and can introduce irrelevant rules.

## Task context

`schemas/task_context.schema.json` is the machine contract. The context records:

- task mode, input kind, and actual/claimed format state;
- file preflight status when file input is used;
- language and product scope when known;
- whether an approved project glossary is available;
- whether aligned bilingual units exist;
- whether structured output is required;
- whether external evidence is still needed or explicitly requested;
- whether public research is permitted;
- whether an approved scoped resource already resolves the question;
- whether repair is requested and authorized;
- material risk tags.

Unknown facts must remain unknown. Do not set a signal to `true` merely to make a
resource available.

## Routing principles

### Input and preflight first

File input routes the runtime preflight/ingest gate. Inline text does not. A file
extension alone cannot populate a trusted task format; use verified preflight output.

### Mode next

Mode resources establish the smallest task-specific policy set. Format, risk,
evidence, deterministic QA, output-contract, and repair resources are additive and
conditional.

### Format only when material

Structured-format policy is routed for formats where native structure, layout,
macros, links, or other non-text content can affect the result. File-format
detection is a separate preflight concern; extension alone must not be treated as
proof of actual format.

### Evidence only when needed

If an approved resource resolves the task within its declared scope and the user did
not request external verification, do not route public-search strategy merely to
repeat the same conclusion. Explicit research requests override that suppression,
subject to research permission.

### Deterministic QA requires aligned units

`references/15_DETERMINISTIC_BILINGUAL_QA.md` is routed only when aligned bilingual
units exist in a mode that can use them. A deterministic finding is
`POTENTIAL_ISSUE`; it is not evidence, a semantic verdict, confidence, or repair
authorization.

### Repair is isolated

Repair-specific QA/release rules are routed only after repair is authorized.
An audit or review request does not authorize repair.

### Worked examples are narrow

Risk tags may route up to the configured maximum number of worked-example sections.
Risk-tag order represents relevance order when the cap is exceeded. Do not load the
full worked-example file unless a separate explicit reason requires it.

## Re-routing

The resource plan is not immutable. Rebuild it when a material state transition
occurs, for example:

- a project glossary becomes available;
- source/target alignment is completed;
- a technical claim is discovered;
- an approved source fails to resolve the term;
- the user explicitly requests external verification;
- repair becomes authorized.

Re-routing must only add or remove resources justified by the new state.

## Validation

Generate a plan with:

```bash
python scripts/route_resources.py task_context.json --output resource_plan.json
```

The script validates both the input context and generated plan. Package maintenance
must keep router paths, schemas, example route IDs, and regression fixtures in sync.

## Ingest handoff

A resource plan controls instruction loading; it does not certify parser output.
After file ingestion, validate coverage with
`schemas/ingest_report.schema.json` / `scripts/validate_ingest.py`.

A `PARTIAL` ingest report keeps its gaps visible through final delivery. A failed
ingest gate cannot be converted into full document coverage by later semantic
reasoning.

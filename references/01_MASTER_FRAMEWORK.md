# Master framework

DBabel is data-light and method-heavy. Its runtime is split into a small control
plane and task-specific resources so the agent does not load the whole methodology
for every request.

```text
                         DBABEL
                           |
                 Runtime Control Plane
                           |
          +----------------+----------------+
          |                |                |
     Task Context      Format/Capability   Resource Router
          |               Preflight             |
          +----------------+--------------------+
                           |
                      load_now only
                           |
       +-------------------+-------------------+
       |                   |                   |
 Runtime Knowledge    Document Engine    Review Governance
       |                   |                   |
 user resources          ingest              evidence
 standards/vendor        structure           decisions
 approved glossary       alignment           repair gates
 web evidence            translation         audit trail
       |                   |                   |
       +-------------------+-------------------+
                           |
                    Accuracy Core
                 deterministic checks
                           |
                    Semantic Judge
                           |
          KEEP / REPLACE / PROTECT
          REVIEW / OUT_OF_SCOPE_CLAIM
```

`Runtime Knowledge` means sources supplied or retrieved for the current task. It is
not a DBabel-owned termbase.

The deterministic Accuracy Core detects mechanical inconsistencies after alignment.
It never establishes semantic correctness or authorizes a repair.

For file tasks, parser selection occurs only after content-format and capability
preflight. Parser availability still does not prove ingest completeness; actual
coverage is validated after parsing.

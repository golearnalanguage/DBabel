# Architecture

DBabel separates runtime context, terminology evidence, review decisions and document delivery.

```text
User request / files
        |
        v
+-----------------------+
|  Runtime control      |
|  - Task Context       |
|  - Format Probe       |
|  - Capability Probe   |
|  - Resource Router    |
+-----------+-----------+
            |
            | load_now only
            v
+-----------------------+       +----------------------+
| Task-specific policy  |<----->| Runtime knowledge    |
| and document handling |       | user resources       |
+-----------+-----------+       | standards/vendor docs|
            |                   +----------------------+
            v
+-----------------------+
| Ingest validation     |
| structure / coverage  |
+-----------+-----------+
            |
            v
+-----------------------+
| Terminology /         |
| translation reasoning |
+-----------+-----------+
            |
            +---------------------+
            |                     |
            v                     v
+-----------------------+   +-----------------------+
| Accuracy Core         |   | Evidence assessment   |
| deterministic QA      |   | semantic adjudication |
+-----------+-----------+   +-----------+-----------+
            |                           |
            +-------------+-------------+
                          v
                 Human review decisions
                          |
                          v
                 Agent language recheck
                 (suggestions -> human review)
                          |
                          v
                 Final / checkpoint gate
                          |
                          v
                 round-trip / scoped output
```

The repository contains workflow code, schemas, policies, templates, adapters and synthetic tests. Project documents and terminology are supplied at runtime.

Project glossaries remain user/project data. Only `PROJECT_APPROVED` entries are
eligible for deterministic enforcement within their declared scope.

The Accuracy Core checks literal integrity and approved terminology conditions. The Agent evaluates meaning and evidence; the reviewer records decisions; the export adapter verifies the resulting copy.

Format probing is bounded and non-executing. Optional parser/detector backends are
capabilities, not mandatory dependencies. A selected parser must still be followed
by ingest validation before full coverage can be claimed.

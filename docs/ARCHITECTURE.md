# Architecture

DBabel is intentionally data-light and method-heavy.

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
                 QA / repair gate
                          |
                          v
                 round-trip / output
```

The public repository owns workflow code, schemas, policies, templates, adapters,
and synthetic tests. It does not ship a vendor terminology corpus.

Project glossaries remain user/project data. Only `PROJECT_APPROVED` entries are
eligible for deterministic enforcement within their declared scope.

The Accuracy Core is deliberately narrower than semantic review: it detects
mechanical integrity and approved terminology conditions, but does not establish
technical truth, evidence quality, or repair authorization.

Format probing is bounded and non-executing. Optional parser/detector backends are
capabilities, not mandatory dependencies. A selected parser must still be followed
by ingest validation before full coverage can be claimed.

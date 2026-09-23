# Architecture

DBabel is intentionally data-light and method-heavy.

```text
Agent
  |
  +-- DBabel instructions/policies
  |
  +-- runtime user resources (optional)
  |
  +-- search/browser/document tools (optional)
  |
  +-- MT/LLM provider (optional)
  |
  +-- project-local glossary/TM (optional, owned by user)
```

The public DBabel repository owns only the workflow, schemas, policies, templates, and synthetic tests. Terminology data remains external/runtime unless a separately licensed dataset is created later.

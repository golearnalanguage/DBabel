# Optional format backends

DBabel's default format probe uses only the Python standard library. Optional
backends are adapters, not bundled third-party code. DBabel never installs or
invokes them automatically merely because they are mentioned here.

The machine-readable source of selection behavior is
`config/format_registry.yaml`. This document explains the human-facing rationale and
records upstream facts that matter to DBabel's runtime compatibility model.

## Selection principles

- Prefer the built-in probe for identity checks and extension/content mismatch.
- Use optional detectors only as a fallback hint when the built-in probe cannot
  identify the content. A hint never overrides stronger container or magic-signature
  evidence.
- Parser availability does not prove ingest success or full coverage. Validate the
  structures actually extracted after parser selection.
- Parser availability does not prove repair capability. Repair requires a backend
  explicitly listed for that format plus DBabel's authorization and round-trip QA
  gates.
- `native_agent` is an externally declared capability. Local scripts cannot infer
  whether the hosting agent can read, write, render, or visually inspect a format.
- Macro-enabled Office files are never assigned a generic automatic repair backend.
- Do not install optional dependencies solely because DBabel lists them. Verify
  upstream requirements, licensing, security posture, and organizational policy.

## Registered backends

| Backend | Role | DBabel compatibility note | Upstream |
|---|---|---|---|
| `builtin_probe` | detector | Standard library only; always available; bounded inspection. | DBabel |
| `filetype` | detector | Small dependency-free magic-number detector; optional fallback hint only. | https://github.com/h2non/filetype.py |
| `python_magic` | detector | Python wrapper around `libmagic`; native `libmagic` must also be available. | https://github.com/ahupp/python-magic |
| `builtin_text` | parser | Basic local access for text-like formats; not a DOM, Office-layout, or rendering engine. | DBabel |
| `python_docx` | parser | Current upstream metadata requires Python 3.9+; useful for DOCX structure. | https://github.com/python-openxml/python-docx |
| `python_pptx` | parser | Current upstream metadata requires Python 3.8+; useful for PPTX structure. | https://github.com/scanny/python-pptx |
| `openpyxl` | parser | XLSX/XLSM-focused library; formula/macro fidelity still requires DBabel-specific checks. | https://foss.heptapod.net/openpyxl/openpyxl |
| `pypdf` | parser | Current upstream metadata requires Python 3.9+; text-level PDF access does not replace layout validation. | https://github.com/py-pdf/pypdf |
| `markitdown` | parser | Broad conversion backend; current upstream releases require Python 3.10+. | https://github.com/microsoft/markitdown |
| `docling` | parser | Broad structured-document backend; current upstream releases require Python 3.10+. | https://github.com/docling-project/docling |
| `tika` | parser | Broad detector/parser family with an external Java/server runtime dimension. | https://tika.apache.org/ |
| `native_agent` | parser | Hosting-agent capability declared explicitly rather than auto-detected locally. | runtime-specific |

Compatibility facts can change upstream. DBabel's `probe_capabilities.py` checks the
current environment rather than assuming that a listed project is installed or
usable.

## Verified upstream characteristics

The following facts are relevant to the current registry design:

- `filetype.py` describes itself as dependency-free and magic-number based, requiring
  only a short header for its own detection logic; DBabel still treats it as an
  optional hint rather than authoritative format proof.
- `python-magic` is a wrapper over `libmagic`; installing the Python package alone is
  insufficient when the native library or magic database is unavailable.
- `python-docx` and `python-pptx` are format-focused Office libraries rather than
  generic document converters.
- `pypdf` is a Python PDF library; DBabel does not infer visual/layout coverage from
  text extraction alone.
- MarkItDown converts multiple formats to Markdown and currently requires Python
  3.10+, so it cannot be a mandatory backend while DBabel supports Python 3.9.
- Docling currently requires Python 3.10+ and exposes a broader structured-document
  pipeline; it is therefore optional for the same compatibility reason.
- Apache Tika explicitly distinguishes content detection from parser support: a
  format may be detected even when no parser can extract its content. This is one
  reason DBabel models format detection, parser availability, and ingest coverage as
  separate gates.

## Detector adapter contract

Optional detector adapters under `plugins/format_backends/` expose:

```python
available() -> bool
probe(path: pathlib.Path) -> dict | None
```

A successful `probe()` returns only a hint with `format`, `confidence`, and
`evidence`. The core detector remains responsible for conflict handling and final
schema validation.

## Installation policy

No optional backend belongs in `requirements-dev.txt` merely to make it discoverable.
The core validation environment stays small and Python-3.9-compatible. A user or
hosting environment may install a backend explicitly when its format coverage and
runtime requirements are appropriate.

DBabel does not copy third-party backend source code into this repository. See
`THIRD_PARTY_NOTICE.md` for rights and dependency boundaries.

# Research basis

DBabel's design follows established terminology, localization, and interchange
principles without redistributing standards text or vendor terminology datasets.
These sources inform design choices; they do **not** make DBabel conformant with a
standard unless a specific adapter or conformance claim is implemented and tested.

## Terminology and localization references

- ISO 704:2022 — *Terminology work — Principles and methods*.
  Concept/designation-oriented terminology work informs DBabel's separation of
  concepts, designations, scope, and evidence.
  https://www.iso.org/standard/79077.html
- ISO 16642:2025 — *Management of terminology resources — Terminological markup
  framework*. Its terminology-resource metamodel is relevant to future interchange
  adapters and to keeping concept/scope data distinct from presentation formats.
  https://www.iso.org/standard/87351.html
- ISO 30042:2019 — *Management of terminology resources — TermBase eXchange (TBX)*.
  TBX informs terminology-resource interoperability planning.
  https://www.iso.org/standard/62510.html
- W3C Internationalization Tag Set (ITS) 2.0 — includes Translate, Terminology, and
  Localization Quality Issue data categories.
  https://www.w3.org/TR/its20/
- OASIS XLIFF 2.1 — distinguishes translatable text from inline codes and other
  non-linguistic content such as placeholders. This is relevant to DBabel's
  protected-token and bilingual-unit integrity model.
  https://docs.oasis-open.org/xliff/xliff-core/v2.1/xliff-core-v2.1.html
- NIST CSRC Glossary — illustrates why a term-definition pair must be interpreted in
  the context of its source publication rather than treated as context-free truth.
  https://csrc.nist.gov/glossary

DBabel currently does **not** claim TBX, TMX, or XLIFF compatibility. The public
project-glossary and bilingual-unit schemas are DBabel-native contracts. Interchange
adapters remain separate work and must preserve provenance, scope, and protected
content when implemented.

## Document and runtime implementation references

The built-in format probe uses Python's standard library and bounded inspection.
Optional third-party detectors/parsers are capability backends, not normative
sources and not mandatory dependencies. See
[optional format backends](../plugins/FORMAT_BACKENDS.md) for the registered
projects, compatibility notes, and upstream links.

The distinction between format detection and parsing is deliberate: a tool may be
able to identify a format without being able to extract all of its text, structure,
layout, formulas, comments, macros, or embedded objects. DBabel therefore requires a
separate ingest-coverage gate after parser selection.

Vendor documentation and glossaries should be searched at runtime according to the
candidate's vendor/product/version/text-role scope; they are not copied into DBabel.

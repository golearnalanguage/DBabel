# DBabel package index

## Use the Skill

- [README](README.md) · [中文说明](README.zh-CN.md)
- [Runtime kernel](SKILL.md)
- [Agent integration](docs/AGENT_INTEGRATION.md) · [Capabilities](docs/AGENT_CAPABILITY_MATRIX.md)
- [Architecture](docs/ARCHITECTURE.md) · [Local tooling](docs/LOCAL_TOOLING.md)
- [Examples](examples/) · [Report templates](templates/)

## Progressive runtime

- [Resource router](config/resource_router.yaml)
- [Workflow state machine](config/workflow.yaml)
- [Format registry](config/format_registry.yaml)
- [Resource-routing policy](references/16_PROGRESSIVE_RESOURCE_ROUTING.md)
- [Runtime preflight and ingest validation](references/17_RUNTIME_PREFLIGHT_AND_INGEST_VALIDATION.md)
- [Runtime-plan builder](scripts/prepare_runtime.py)
- [Resource router CLI](scripts/route_resources.py)
- [Format detector](scripts/detect_document_format.py)
- [Capability probe](scripts/probe_capabilities.py)
- [Document preflight](scripts/preflight_document.py)
- [Ingest validator](scripts/validate_ingest.py)
- [Optional format backends](plugins/FORMAT_BACKENDS.md)

## Translation Playbook

- [Translation and MT policy](references/07_TRANSLATION_AND_MT_POLICY.md)
- [Technical translation playbook](references/18_TECHNICAL_TRANSLATION_PLAYBOOK.md)
- [Machine-readable technique registry](config/translation_techniques.yaml)
- [Technique registry schema](schemas/translation_techniques.schema.json)
- [Technique annotation schema](schemas/technique_annotation.schema.json)
- [Technique signal observation schema](schemas/technique_signal_observations.schema.json)
- [Technique candidate report schema](schemas/technique_candidate_report.schema.json)
- [Technique candidate router](scripts/suggest_translation_techniques.py)
- [Candidate-routing example](examples/technique_signal_observations.json)

## Accuracy Core

- [Project terminology resolution](references/14_PROJECT_TERMINOLOGY_RESOLUTION.md)
- [Deterministic bilingual QA policy](references/15_DETERMINISTIC_BILINGUAL_QA.md)
- [Project glossary schema](schemas/project_glossary.schema.json)
- [Project glossary CSV template](templates/project_glossary.csv)
- [Bilingual unit schema](schemas/bilingual_unit.schema.json)
- [Deterministic QA report schema](schemas/deterministic_qa_report.schema.json)
- [Glossary validator](scripts/validate_glossary.py)
- [Glossary loader/normalizer](scripts/glossary_io.py)
- [Bilingual integrity checker](scripts/check_bilingual_integrity.py)
- [Accuracy Core regression tests](tests/test_accuracy_core.py)

## Review Workbench

- [Review Workbench contract](docs/REVIEW_WORKBENCH.md)
- [Local Workbench server](scripts/start_review_workbench.py)
- [Review Session builder](scripts/create_review_session.py)
- [Portable Review builder](scripts/build_portable_review.py)
- [Portable decision importer](scripts/import_review_decisions.py)
- [DOCX bilingual-unit extractor](scripts/extract_docx_bilingual_units.py)
- [DOCX native exporter](scripts/export_reviewed_document.py)
- [Review bundle validator](scripts/validate_review_bundle.py)
- [Review schemas](schemas/)
- [Review Workbench regression tests](tests/)

## Workflow resources

- [Review policies](references/)
- [Source policy](config/source_policy.yaml)
- [File policy](config/file_policy.yaml)
- [Search query templates](config/search_query_templates.yaml)
- [Worked technical-translation examples](examples/technical_translation_review_examples.zh-CN.md)
- [Example router](config/example_router.yaml)
- [Output contract](references/11_OUTPUT_AND_DATA_CONTRACTS.md)

## Schemas and validation

- [Schemas](schemas/)
- [Package checker](scripts/check_package.py)
- [Report validator](scripts/validate_report.py)
- [Regression tests](tests/)
- [Behavioral evaluation](tests/BEHAVIORAL_EVAL.md)
- [Validation dependencies](requirements-dev.txt)
- [Checksums](MANIFEST.sha256)

## Project information

- [Research basis](docs/RESEARCH_BASIS.md) · [Roadmap](docs/ROADMAP.md)
- [Contributing](CONTRIBUTING.md) · [Changes](CHANGELOG.md)
- [License](LICENSE) · [Notice](NOTICE) · [Third-party notice](THIRD_PARTY_NOTICE.md)
- [Security](SECURITY.md) · [Scope notice](DISCLAIMER.md)

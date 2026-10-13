# Third-party names, sources, and rights

DBabel may instruct Agents to consult standards bodies, public terminology
resources, official database-vendor documentation, release notes, product UI, and
other authoritative sources at runtime.

DBabel does **not** redistribute a vendor terminology database, scraped glossary
corpus, licensed standards text, proprietary translation memory, customer document,
or third-party documentation corpus in this repository.

## Adopted components

DBabel first-party source and documentation use [Apache-2.0](LICENSE). The following upstream projects retain their original licenses and copyrights. DBabel calls their public APIs; these entries credit upstream authors and maintainers, rather than identifying them as contributors to DBabel. Upstream implementation files are not copied into the first-party modules.

Runtime integrations are pinned in [requirements-integration.txt](requirements-integration.txt), independently of the Python 3.9-compatible core validation dependencies. Python version markers leave unsupported optional integrations unavailable.

| Upstream project / credited authors | Locked version | Original license | DBabel use |
|---|---|---|---|
| [OpenAI Python SDK](https://github.com/openai/openai-python), OpenAI and contributors | 3.29.0 | [Apache-2.0](https://github.com/openai/openai-python/blob/main/LICENSE) | Optional official SDK provider adapter; Python 3.10+ |
| [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python), Anthropic, PBC. and contributors | 1.13.0 | [MIT](https://github.com/anthropics/anthropic-sdk-python/blob/main/LICENSE) | Optional official Messages SDK provider adapter; Python 3.10+ |
| [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz), Max Bachmann and contributors | 3.14.6 | [MIT](https://github.com/rapidfuzz/RapidFuzz/blob/main/LICENSE) | Local similarity candidates in translation memory; Python 3.11+; candidates do not grant approval |
| [lxml](https://github.com/lxml/lxml), Infrae and lxml contributors | 6.1.3 | [BSD and bundled-component licenses](https://github.com/lxml/lxml/blob/master/LICENSES.txt) | Optional TMX 1.4 XML reader/writer, with entity/network loading disabled |

lxml wheels contain separately licensed native libraries. Its upstream `LICENSES.txt` identifies zlib, iconv, libxml2, libxslt and libexslt, as well as ElementTree/CPython-derived portions. Preserve the complete license set from the actual installed artifact; the BSD description of the Python library does not replace those licenses.

## Development verification components

These tools run in development tests and CI. They are not invoked by ordinary translation or review sessions.

| Upstream project / credited authors | Locked version / owner | Original license | DBabel use |
|---|---|---|---|
| [Playwright](https://github.com/microsoft/playwright), Microsoft and contributors | 1.64.0, [package.json](package.json) and [package-lock.json](package-lock.json) | [Apache-2.0](https://github.com/microsoft/playwright/blob/main/LICENSE) | Real browser review, exchange, recovery and export smoke tests |
| [axe-core](https://github.com/dequelabs/axe-core), Deque Systems and contributors | 4.11.0, package-lock.json | [MPL-2.0](https://github.com/dequelabs/axe-core/blob/develop/LICENSE) | Accessibility checks injected by tests; no production script injection |
| [Hypothesis](https://github.com/HypothesisWorks/hypothesis), David R. MacIver and contributors | 6.169.0, [requirements-property.txt](requirements-property.txt) | [MPL-2.0](https://github.com/HypothesisWorks/hypothesis/blob/master/LICENSE.txt) | Generated document/anchor/QA-state regression cases on Python 3.11+ |

The core development requirements already use [jsonschema](https://github.com/python-jsonschema/jsonschema) (MIT) and [PyYAML](https://github.com/yaml/pyyaml) (MIT). Desktop distributions include CPython and its runtime dependencies, including OpenSSL. [The retained runtime inventory](third_party/python-runtime/20260924/README.md) contains the original license directory and build metadata from the verified matching upstream archive. The desktop packager checks the runtime build, copies this inventory and exports the actual installed Python package licenses into `Contents/Resources/licenses`. Original third-party terms continue to apply to those components.

[config/third_party_components.json](config/third_party_components.json) provides machine-readable attribution, exact adopted versions, purpose and reference-only classifications. `python scripts/check_third_party.py` checks its adopted set against the Python dependency pins and Node lock file. For an installed release environment, `python scripts/check_third_party.py --installed --output output/license-inventory` retains actual Python and installed Node license/NOTICE files unchanged, including wheel `LICENSES.txt`, and writes their SHA-256 inventory. Use `--distribution-path /absolute/site-packages` to audit a specific bundled Python tree. Select a new output directory each time. Unknown metadata, version drift or missing declaration material is reported for review rather than assigned an invented license. Standalone Python/OpenSSL runtimes and browser binaries outside these artifact roots require a separate distribution inventory.

## Research and architecture references

[REA](https://github.com/morluto/rea) informed provenance, provider-boundary and verification strategies. [OmegaT](https://github.com/omegat-org/omegat), [Translate Toolkit](https://github.com/translate/translate) and [Okapi Framework](https://gitlab.com/okapiframework/Okapi) informed translation-memory, interchange and Office-filter evaluation. These projects are references only: their code is not copied, packaged, installed or run by the implementations listed above. Their authors retain their own rights and licenses.

The TMX implementation is an independent narrow adapter using lxml. It does not claim full OmegaT/Translate Toolkit interoperability, XLIFF/TBX support, or Okapi filter coverage. Docling and LanguageTool remain optional evaluation candidates; no PDF model pipeline or LanguageTool service is bundled by these changes.

## Optional format backends

DBabel registers several third-party detector/parser projects as optional runtime
backends, including `filetype.py`, `python-magic`, `python-docx`, `python-pptx`,
`openpyxl`, `pypdf`, MarkItDown, Docling, and Apache Tika. Their names and upstream
links are used for capability discovery and interoperability documentation.

Those projects are **not vendored into DBabel and are not installed automatically**.
Installing or using one creates a separate dependency relationship governed by that
project's own license, security model, system requirements, and release lifecycle.
Some backends also require native libraries, Java, servers, model downloads, or
other runtime components beyond the Python package itself.

See [optional format backends](plugins/FORMAT_BACKENDS.md) for DBabel's registration
and compatibility notes. The machine-readable registry records selection behavior,
not ownership, endorsement, certification, or a guarantee of upstream compatibility.

## Rights and source use

All trademarks, product names, service names, documentation, standards, source
code, and other third-party materials remain the property of their respective
owners or rights holders and remain subject to their own licenses, terms, and access
conditions.

Mentioning a vendor, product, standard, or open-source project in DBabel does not
imply sponsorship, endorsement, affiliation, certification, or ownership. The
project's use of such names is limited to identification, terminology analysis,
interoperability research, capability routing, and documentation workflows.

A runtime Agent should quote or store only the minimum evidence needed for the task
and must respect applicable copyright, access controls, licensing terms,
confidentiality obligations, and organizational policy.

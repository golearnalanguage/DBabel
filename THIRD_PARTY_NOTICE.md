# Third-party names, sources, and rights

DBabel may instruct Agents to consult standards bodies, public terminology
resources, official database-vendor documentation, release notes, product UI, and
other authoritative sources at runtime.

DBabel does **not** redistribute a vendor terminology database, scraped glossary
corpus, licensed standards text, proprietary translation memory, customer document,
or third-party documentation corpus in this repository.

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

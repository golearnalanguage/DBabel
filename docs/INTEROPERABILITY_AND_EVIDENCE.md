# TMX interchange and local evidence cache

[简体中文](INTEROPERABILITY_AND_EVIDENCE.zh-CN.md) · [Documentation index](INDEX.md)

The commands below add local artifacts to the existing review workflow. TMX imports create unapproved candidates; evidence checks report affected review scope. Neither command changes `.dbreview` decisions or approves a translation.

## TMX 1.4

Install the optional integrations into your selected Python environment:

```bash
python -m pip install -r requirements-integration.txt
```

Export existing local memory to a new TMX file:

```bash
python scripts/tmx_exchange.py export --memory --output memory.tmx
```

The exporter calls the same `runtime.translation_memory.export_entries()` API used by the memory view. Source/target text and language tags remain exact; `x-dbabel-record` properties retain text role, scope, original decision metadata and provenance fields when present. Rejected records are excluded by default. `--include-rejected` retains them with their DBabel status for inspection; another CAT tool may ignore that status, so do not use that output as an approved translation memory. `--entries entries.json` can export an explicit JSON list instead. Existing output files are never overwritten.

Create a candidate receipt for one exact language pair:

```bash
python scripts/tmx_exchange.py import incoming.tmx --source-language en --target-language zh-CN --output candidates.json
```

The reader supports unnamespaced TMX with `version="1.4"`, one header/body, and plain `<seg>` text. An adjacent locale is not substituted for the requested tag. Duplicate/missing variants, unsupported extensions and inline elements produce `UNSUPPORTED` candidates. Their complete unit/segment XML remains in `provenance`, and affected text fields are null for unresolved inline content. A known plain candidate is still `USER_REVIEW`; foreign metadata never creates a local human decision. Missing scope stays empty and missing text role becomes `UNKNOWN`.

TMX input is bounded to the existing 16 MiB document intake limit. XML entities are rejected, and external DTD/entity/network loading is disabled. This is a plain-segment exchange CLI: it does not import candidates into the memory database or Workbench, reconstruct inline codes, validate every TMX dialect, or implement TBX/XLIFF. Use the JSON receipt for a separate scoped human review. Other CAT tools may drop custom properties, so inspect the returned metadata before relying on a round trip.

## Evidence source snapshots

Prepare one existing [evidence record](../schemas/evidence.schema.json), a readable local source file and a JSON scope object. Scope should state the relevant project/product/version/text role; an empty or missing fact does not mean every project or version.

```bash
python scripts/evidence_cache.py record --cache /absolute/path/evidence-cache --evidence evidence.json --source opened-reference.txt --scope scope.json --unit-id U001 --expires-at 2026-12-01T00:00:00Z
python scripts/evidence_cache.py check --cache /absolute/path/evidence-cache --scope current-scope.json --session project.dbreview --output evidence-check.json
```

`record` validates the existing evidence contract, retains a private SHA-256-addressed source snapshot and an immutable, integrity-checked record. Repeat `--unit-id` for dependent units. The original locator, authority/context/version assessments and evidence state are preserved. Identical calls reuse the same semantic record. Source and cache-record files share the 16 MiB intake limit. Expiry is optional and requires an explicit timezone.

`check` compares the current local source bytes, the retained snapshot's integrity, explicit expiry and current scope when supplied. A changed/missing source, scope change or expiry reports `STALE`, its reason and affected unit IDs. It retains `source_evidence_state`, including `CONFLICTING` or `INSUFFICIENT`, and never upgrades that assessment. `--session` reads `units.jsonl` evidence links to include additional affected units; it does not edit session evidence, decisions, notes or QA.

Check exit statuses are `0` for all-current retained records, `2` when a record needs review, and `1` for invalid data, tampered snapshots/records or I/O failure. The report is written to a new path. A current local hash establishes unchanged supplied bytes; live web freshness, semantic authority and current scope require their own review. After a reported dependency changes, reopen the relevant sources, revisit affected suggestions with the reviewer, and run fresh applicable QA/export gates.

The cache stores local source material. Choose a cache directory outside the repository, keep it with private project data and include it in user-controlled backups. The commands fetch no URLs or credentials. Exclude project caches from release packages.

## Adopted projects and validation

lxml supplies the XML implementation. The memory similarity, official SDK adapters and development verification dependencies are listed with exact versions and original licenses in [THIRD_PARTY_NOTICE.md](../THIRD_PARTY_NOTICE.md). REA, OmegaT, Translate Toolkit and Okapi are architecture/format references; their code is not embedded in these commands.

The [machine-readable component registry](../config/third_party_components.json) is checked against exact dependency/Node lock pins. Release preparation can retain installed artifact licenses and notices:

```bash
python scripts/check_third_party.py
python scripts/check_third_party.py --installed --distribution-path /absolute/site-packages --output output/license-inventory
```

The inventory preserves original license bytes, wheel native-library notices and SHA-256 receipts. Exit `2` means metadata, installed-version drift or missing notice material needs review; no license is inferred. Standalone Python/OpenSSL runtimes and browser binaries outside the selected trees require separate inventory. The output directory must be new.

Focused checks:

```bash
python -m unittest discover -s tests -p 'test_tmx_exchange.py' -v
python -m unittest discover -s tests -p 'test_evidence_cache.py' -v
```

TMX tests require lxml and are skipped in a core-only environment. An integration environment must run them without skips. Evidence-cache tests use the existing core validation dependencies.

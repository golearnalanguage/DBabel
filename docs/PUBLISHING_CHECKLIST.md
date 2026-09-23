# Public GitHub publishing checklist

Before publishing:

- [ ] Repository/package name is consistently `DBabel` / `dbabel`.
- [ ] `SKILL.md` states that DBabel ships no terminology database.
- [ ] Examples/tests are synthetic or clearly reusable.
- [ ] Customer names, internal URLs, private hostnames, account IDs, credentials, API keys, tokens, and proprietary project details are absent.
- [ ] No company-internal glossary/SOP is included unless explicitly authorized for publication.
- [ ] No downloaded vendor manual, scraped glossary corpus, or licensed standards text is bundled.
- [ ] Git history has been inspected for secrets, not just the working tree.
- [ ] `LICENSE` points to PolyForm Noncommercial License 1.0.0 and the copyright notice is correct.
- [ ] README describes DBabel as source-available/noncommercial, not OSI-approved open source.
- [ ] `THIRD_PARTY_NOTICE.md`, `DISCLAIMER.md`, and `SECURITY.md` are present.
- [ ] Repository description/topics are configured.
- [ ] Issue templates and private security-reporting path are configured.
- [ ] YAML/JSON files validate.
- [ ] `MANIFEST.sha256` validates.
- [ ] Release archive passes ZIP integrity testing.
- [ ] Release tag/version and release notes match the files.

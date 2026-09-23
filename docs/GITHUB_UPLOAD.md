# Upload DBabel to GitHub

This package is prepared so that its contents can become the repository root.

## 1. Create the empty repository

Recommended settings:

- Repository name: `dbabel`
- Visibility: Public
- Add README: Off
- Add `.gitignore`: None
- Add license: **No license**

Select `No license` because this package already contains the PolyForm Noncommercial licensing notice and GitHub's standard chooser may not provide it.

Suggested description:

`Evidence-driven database terminology auditing and localization workflow for AI agents.`

Suggested topics:

`database`, `terminology`, `localization`, `translation`, `i18n`, `l10n`, `sql`, `technical-writing`, `ai-agent`, `agent-skill`, `terminology-management`, `machine-translation`

## 2. Unpack the release locally

The repository root should contain `README.md`, `SKILL.md`, `LICENSE`, `NOTICE`, `.github/`, `references/`, `config/`, `schemas/`, and the other files directly. Do not upload only the ZIP as the repository contents.

## 3. Initialize and push

Replace `<YOUR-REPOSITORY-URL>` with the repository URL shown by GitHub.

```bash
git init
git add .
git commit -m "Initial public release: DBabel v1.2.0"
git branch -M main
git remote add origin <YOUR-REPOSITORY-URL>
git push -u origin main
```

If the remote repository already contains an automatically created README or license, reconcile that commit before pushing instead of force-pushing blindly.

## 4. Repository settings after push

- add the description and topics above;
- enable private vulnerability reporting if available;
- check the Issues templates;
- create a `v1.2.0` release/tag;
- attach the release ZIP and SHA-256 file as release assets if desired.

## 5. Final public check

Run through `docs/PUBLISHING_CHECKLIST.md` before announcing the repository.

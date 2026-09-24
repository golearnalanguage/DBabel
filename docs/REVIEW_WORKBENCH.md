# DBabel Review Workbench — v1.5 development contract

Current released DBabel Skill/package version: **1.4.0**.

Current Review Workbench development contract: **1.5.0-dev**.

The Workbench development version is intentionally separate from the released
package version until a formal v1.5.0 release is prepared. It does not by itself
create or move a Git tag or GitHub Release.

The Review Workbench adds a human approval layer between DBabel findings/QA and any
native-format repair. It is intentionally not a full CAT platform.

## Invariants

- A DBabel suggestion is not user approval.
- `POTENTIAL_ISSUE` remains a deterministic QA classification, not a semantic error verdict.
- `USER_EDITED` content is rechecked before export.
- `UNREVIEWED`, `DEFERRED`, and `BLOCKED` units prevent export.
- A remaining deterministic `ERROR` prevents export unless the user explicitly chooses
  `WAIVED`, records a non-empty reason, and the waiver matches the current stable issue
  fingerprint.
- The original document SHA-256 must still match the review session before native export.
- Native export requires every review unit to have `ALIGNED` bilingual alignment.
  `AMBIGUOUS`, `SPLIT`, `MERGED`, and `UNALIGNED` units remain reviewable but
  block native write-back until a dedicated alignment/write-back path exists.
- The original document is never overwritten.
- A written output is not `VERIFIED` until round-trip checks pass.

## Review bundle

A `.dbreview` directory contains review metadata and decisions, not a second copy of the
customer document by default:

```text
Manual.dbreview/
  session.json
  units.jsonl
  issues.json
  evidence.json
  decisions.json
  events.jsonl
  anchors.json
  original.sha256
```

The local path of the original is not stored unless the creator explicitly requests a
path hint.

## Desktop workflow

```bash
python scripts/create_review_session.py units.jsonl \
  --qa-report qa-report.json \
  --audit-report audit-report.json \
  --original translated.docx \
  --output translated.dbreview

python scripts/start_review_workbench.py translated.dbreview \
  --original translated.docx \
  --output translated.reviewed.docx
```

The server binds only to `127.0.0.1`, chooses an available port, uses a random session
token, sends restrictive browser security headers, and has no external frontend runtime.

## Portable workflow

```bash
python scripts/build_portable_review.py translated.dbreview \
  --output translated-review.html
```

The generated HTML is self-contained and makes no network requests. It can export a
`decisions.json` file, which is imported on a machine that has the review bundle:

```bash
python scripts/import_review_decisions.py \
  translated.dbreview translated.docx.decisions.json
```

Portable review never writes the native document itself.

## DOCX native export

The initial native adapter supports `.docx` only. It uses exact OOXML paragraph anchors,
verifies the original package hash and anchor text, patches existing `w:t` nodes rather
than rebuilding the document, refuses ambiguous anchors, refuses in-place overwrite,
and verifies reviewed target text plus non-target paragraph text after writing.

```bash
python scripts/export_reviewed_document.py translated.dbreview \
  --original translated.docx \
  --output translated.reviewed.docx \
  --receipt export-receipt.json
```

DOCM/PPTX/XLSX/PDF native repair is not claimed by this development slice.

## Visual contract

The desktop Workbench has a fixed review-oriented shell derived from the DBabel brand
lockup and the approved Review Workbench visual reference in
`assets/dbabel-review-workbench-preview.png`.

The visual hierarchy is part of the product contract, not a decorative mockup:

- the DBabel handwritten wordmark, Tower of Babel, `REVIEW WORKBENCH`, and
  `DATABASE TERMINOLOGY AUDIT` lockup stays at the upper-left;
- the left rail owns navigation and persistent review filters;
- the document identity/search area stays above the review surface;
- Total Segments, Reviewed, With Issues, and To Review counters remain visible before
  the bilingual grid;
- the center pane is a bilingual segment table with Source, Target, Status, and Issues;
- the right inspector owns the selected segment, suggestion, evidence, terminology/QA
  labels, human decision controls, notes, and export-gate state;
- `Accept Suggestion` is the primary action; `Keep Current`, `Edit`, `Defer`, `Block`,
  and `Waive` remain distinct human decisions rather than aliases;
- Export remains visibly locked until the export contract authorizes it.

The implementation uses local HTML/CSS/JavaScript and local image assets only. No CDN,
remote font, remote script, or remote image is required at runtime. The portable HTML
uses the same brand lockup and review hierarchy but collapses the left rail on narrow
screens.

## Appearance contract

The Workbench exposes **Light / Dark / System** appearance modes. `System` follows `prefers-color-scheme`; the selected preference is persisted locally. Long issue labels must wrap or expose their full text rather than being silently clipped. Desktop layout keeps the bilingual segment grid dominant while reserving a persistent inspector on the right; responsive layouts stack the inspector below the grid.

### V5 reference-layout refinement

The desktop and portable reviewers now share the same CSS layout contract. At a
reference desktop viewport around 1600×900, the intended composition is approximately
15% navigation/filter rail, 55% bilingual segment workspace, and 30% selected-segment
inspector. Typography and row density are sized so roughly eight review rows remain
visually readable without shrinking technical text.

Long machine check identifiers are not truncated. The UI may display a concise alias
such as `NUMBER_UNIT`, `PLACEHOLDER`, or `ENV_VAR` while retaining the complete
machine identifier in the underlying review data and the element tooltip. This is a
presentation rule only and never rewrites QA semantics.

The Suggested Translation tab includes a linked-evidence preview when evidence is
available, matching the evidence-first human-review flow. The full Evidence tab remains
available for all linked records.

### V6 brand-shell refinement

The approved shell is now treated as a repository-level visual template rather than a
one-off illustration. The Workbench uses a transparent DBabel brand lockup so the tower,
handwritten wordmark, `REVIEW WORKBENCH`, and subtitle visually merge with the rail/header
surface instead of sitting on a white image rectangle. The application UI must not draw
fake operating-system window chrome (minimize, maximize, or close controls); those belong
to the host browser/desktop, not DBabel.

Reference/demo reviewer identity is `clay` with the `CL` avatar. Runtime implementations
may later source reviewer identity from an explicit user/session setting, but the review
contract must never infer or overwrite decision authorship silently. The README preview
uses the approved Workbench template with `clay` and no simulated OS title-bar controls.

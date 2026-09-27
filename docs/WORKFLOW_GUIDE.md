# Local reviewer walkthrough

[简体中文](WORKFLOW_GUIDE.zh-CN.md) · [Documentation index](INDEX.md)

This guide is for a person reviewing translations locally. The Workbench runs without an API key and works offline after dependencies are installed. It does not call a translation model: edit translations yourself or bring proposals from an Agent. Dependency installation and external research may need a connection.

## 1. Install and start

On macOS/Linux, enter your actual download directory first. For this checkout:

```bash
cd /Users/eric/Downloads/DBabel-submit
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
source .venv/bin/activate
python scripts/start_local.py
```

On Windows PowerShell, use `Set-Location "C:\your-folder\DBabel"`, `py -m venv .venv` and `.venv\Scripts\Activate.ps1`, then the same Python commands. The launcher copies the demo to `output/local-demo.dbreview` only on first use; later launches resume its saved decisions.

You can start from any directory with absolute paths:

```bash
/Users/eric/Downloads/DBabel-submit/.venv/bin/python /Users/eric/Downloads/DBabel-submit/scripts/start_local.py
```

Keep the terminal open. Use the complete URL printed for this run, including `#token=`. Select English or Simplified Chinese at the top right; content and notes remain verbatim. Stop with Ctrl+C. If the port is occupied, add `--port 8766`. If a script is missing, check your directory; if a module is missing, install with the same virtual-environment Python. Resume an existing session with `python scripts/start_local.py --bundle /absolute/path/manual.en.dbreview`.

## 2. Upload and inspect

Select **Upload documents**, choose the source and set language tags such as `zh-CN` and `en`. Select **Inspect document** and check format, extracted units, hash and omissions against the original. See [format coverage](DOCUMENT_FORMATS.md).

An existing target file requires one target language and matching segment counts. Check semantic correspondence, then confirm alignment. Equal counts alone do not establish alignment. Split or merged content needs an Agent's explicit alignment map.

Source-only DOCX/TXT/MD with one target language keeps source text as an unreviewed layout template. Enter or accept actual translations before delivery. Multiple languages such as `en,ja` create independent review units; use one session per language for native documents.

Equivalent CLI intake:

```bash
mkdir -p output
python -c "from pathlib import Path; Path('output/source.txt').write_text('主库发送归档日志。\n连接数上限为 1000。\n', encoding='utf-8')"
python scripts/intake_document.py output/source.txt --inspect
python scripts/intake_document.py output/source.txt --source-language zh-CN --target-languages en --output output/manual.en.dbreview
python scripts/start_local.py --bundle output/manual.en.dbreview
```

## 3. Create a session and obtain proposals

**Create session** saves a new `.dbreview` folder with input copies under `inputs/` and extraction scope in `intake.json`. The notification gives the path, normally under `dbabel-sessions/` beside the starting session. Existing sessions remain available.

Give an Agent a JSON review snapshot and this instruction:

```text
Use $dbabel-database-terminology-audit. Read SKILL.md and routed resources.
Translate zh-CN into en in concise technical-manual English. Preserve the
original file's paragraph, cell and run structure and every protected token.
Keep unit IDs, locations, languages and target (the current text) unchanged.
Supply suggested_target plus a specific suggestion_reason for each unit.
For specification entries preserve object, quantity, unit, comparator,
recommendation/requirement and scope. Do not create tables or paragraphs.
Record unresolved context and evidence actually opened. Preserve human
decisions and notes. Create a separate proposal session; do not approve it.
```

Create a proposal session from aligned data with `python scripts/create_review_session.py aligned-units.json --original target.docx --output output/proposals.en.dbreview`. The original must be the same file whose current text and locations the units describe. `target` is current text; `suggested_target` is a proposal. For manual review, continue in the uploaded session instead.

## 4. Add terminology

Open **Terminology → Upload project glossary**, select canonical CSV/JSON, then **Validate and use glossary**. Templates are under `templates/project_glossary.*`. Have an Agent convert a Word/PDF terminology document into that structure, retaining language, product scope, provenance and actual approval status.

```bash
python scripts/validate_glossary.py templates/project_glossary.csv
```

The score is passed applicable term/unit checks divided by all applicable checks, multiplied by 100. Only scoped `PROJECT_APPROVED` entries count; no applicable entries means no score. It measures terminology compliance, not complete translation quality.

## 5. Review and run QA

Filter units, select a row and inspect the source, target, suggestion, reason and evidence. Accept a suggestion, keep current text, edit, defer, block or waive with a reason. Edited text and notes have separate save buttons. Bulk keep/defer applies to your selected units; review the count before confirmation. The interface provides guidance when no actual translation suggestion is available.

Run **Quality Check → Rerun QA** after changes. Inspect numerical, terminology and protected-token findings against the source. A technical claim or meaning check still needs evidence and judgment. Only actual human decisions authorize reviewed text.

## 6. Export review results

The top result selector downloads JSON, CSV, TSV, Markdown, HTML or TXT at any stage, including demo/review-only sessions. HTML provides responsive bilingual columns. JSON preserves decisions, notes, revisions, issues and evidence. Pending rows retain current text.

```bash
python scripts/export_review_results.py output/manual.en.dbreview --format html --output output/manual-review.html
```

## 7. Export the original format

Supported uploaded sessions configure native export automatically from the saved input. Choose FINAL for complete review, or CHECKPOINT for reviewed changes with pending text unchanged. The browser downloads a ZIP containing the native document, receipt, Markdown/JSON handoff and bilingual HTML. Excluded handoff units remain in the document unchanged; they are not deleted.

For explicit DOCX alignment and export:

```bash
python scripts/extract_docx_bilingual_units.py source.docx target.docx --source-language zh-CN --target-language en --output output/docx-units.jsonl
python scripts/create_review_session.py output/docx-units.jsonl --original target.docx --output output/docx-review.dbreview
python scripts/start_review_workbench.py output/docx-review.dbreview --original target.docx --output output/target.reviewed.docx
python scripts/export_reviewed_document.py output/docx-review.dbreview --original target.docx --output output/target.checkpoint-01.docx --export-mode CHECKPOINT
```

CLI output names must be new. DOCX structure and non-text formatting definitions are checked; text length and fonts can still affect wrapping and pagination. Inspect in Word/LibreOffice. TXT/MD preserve line endings and blank lines; review markup in edited lines. Other formats currently produce review results; see the [assessment](NATIVE_EXPORT_ASSESSMENT.md).

## 8. Agent recheck and portable review

Native deliveries already include handoff files. Reports also downloads a standalone Agent handoff:

```bash
python scripts/build_post_review_report.py output/docx-review.dbreview --format md --output output/post-review.md
```

Follow [post-human review](POST_REVIEW_QA.md), checking typos, omissions, terminology, quantities, negation and protected tokens. The Agent returns located proposals bound to revisions and hashes; it does not replace human decisions. Apply chosen changes, rerun QA and export again. `NOT_RUN` means Agent review has not occurred.

For a portable HTML review, use `scripts/build_portable_review.py`; import its decisions into the matching local session with `scripts/import_review_decisions.py`, then rerun local QA. Exact commands and alignment-map details are in the [Workbench manual](REVIEW_WORKBENCH.md).

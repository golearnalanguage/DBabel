# DBabel for macOS

[简体中文](DESKTOP_APP.zh-CN.md) · [Documentation index](INDEX.md)

The macOS app opens the existing Full Local Review Workbench in a native window. It can run a translation project through the current provider runtime, open an existing `.dbreview` session, or open a separate demo copy. Review decisions remain in the session directory. The app does not approve translations automatically.

## Install and open

The packaged Apple Silicon disk image is `output/release/DBabel-macOS-AppleSilicon.dmg`. Open it, drag **DBabel.app** to Applications, then launch it. The packaging command leaves one app bundle and one disk image in the release directory; its temporary build copies are removed. The app bundles Python 3.12, OpenSSL 3 and its runtime dependencies. Demo and new sessions are written to `~/Library/Application Support/DBabel/`; the installed app does not depend on the checkout or `.venv`. This local build is ad-hoc signed and not notarized; a public Developer ID distribution has not been prepared.

To rebuild the disk image from source, use macOS on Apple Silicon with Xcode Command Line Tools and network access for the first dependency download:

```bash
cd /path/to/DBabel
sh scripts/package_macos_app.sh
open output/release/DBabel-macOS-AppleSilicon.dmg
```

For development, `sh scripts/build_macos_app.sh` produces a checkout-bound `output/desktop/DBabel.app`. It uses the prepared `output/build-python` and `output/build-vendor` runtime when present, then falls back to a repository `.venv`. The Swift-only build does not install Python dependencies; run `sh scripts/package_macos_app.sh` to prepare a self-contained build, or install `requirements-dev.txt` into `.venv` before launching the development app. The Python browser launcher remains available on macOS, Windows and Linux through `python scripts/start_local.py`.

The welcome screen and embedded Workbench share macOS window material. An animated DBabel wordmark sits above two entry points: **AI translation** and **Local bilingual review**. The former opens the existing API translation form; the latter has a separate source/target upload, demo and recent-task screen. The top-right controls return to Welcome and toggle appearance or interface language. The Workbench has a visible **Save progress** button and a toolbar action to save and return. The Workbench uses WebKit's optional, non-public canvas switch to reveal the window material; a distributable App Store build needs this compatibility choice reviewed or replaced.

## Translate a document

From Welcome, choose **AI translation**, then a DOCX, TXT, Markdown or XLSX source. Select distinct source and target languages from the menus, such as `zh-CN` and `en`, and enter a concrete text role such as `PROSE`. Select **Configure API service**. Address and model presets include DeepSeek, OpenAI, Gemini, Kimi, Claude compatibility, xAI and Qwen; you can also enter any compatible service URL and exact model ID. Presets only fill fields and do not restrict provider choice. Enter a key issued by that service. The app uses OpenAI-compatible Chat Completions and appends `/chat/completions` to the base URL, so do not include that path in the URL field. Remote services require HTTPS; a local service can use a URL such as `http://127.0.0.1:8000/v1`. For a gateway, enter its user token rather than the key it uses to connect to an upstream channel. Check the provider's own documentation for supported models and compatibility; verify Claude compatibility features against the intended model separately.

The model must be enabled by the chosen service, accessible to the key, and support Chat Completions. **Test model connection** sends one short request through the same code path used by translation, checking the URL, key, model route and response shape; it may incur a small amount of API usage. If a gateway forwards requests, check its upstream channel, model mapping and quota.

The connection test checks only the API; it does not parse the selected document. **Translate and open Workbench** shows format preflight, extraction, translation, deterministic QA, semantic review, session creation and delivery validation. Translation and semantic review show completed units and the current source location. Each successful provider batch is saved immediately. After a network or balance failure, use **Resume this run** on the failure page or **Resume previous run** on Home; saved translations and QA are reused, and only unfinished batches are requested. Keep the source file, language pair and API service configuration unchanged. Runs created before batch checkpoints may need to repeat the interrupted stage, while retaining prior completed stages. XLSX numerical, date, boolean and formula cells stay unchanged. Interrupted responses receive bounded retries; repeatedly truncated batches are split. Technical-literal mismatches are retried and flagged for review when unresolved. Try the [short synthetic walkthrough](../examples/sample_review_workflow.zh-CN.txt), then the [130-unit XLSX example](../examples/sample_long_sop.zh-CN.xlsx).

Leave **Network proxy** blank to use the current macOS system proxy, or enter a custom proxy such as `http://127.0.0.1:1082`. The relevant VPN, private DNS and proxy still need to be running. `TLS`, `SSL`, `Connection reset by peer` or `EOF` means the connection failed before key or model validation. HTTP `401` indicates a rejected token, `403` insufficient access, `404` usually the route or model, and `429` a quota or rate limit. The app does not disable certificate verification to work around connection errors.

No JSON file is needed for first-time setup. If you already have an OpenAI-compatible provider JSON, use **Import JSON…** in the settings sheet. For example, a local provider listening at `127.0.0.1:8000`:

```json
{
  "provider": "openai-compatible",
  "base_url": "http://127.0.0.1:8000/v1",
  "api_key_env": "DBABEL_API_KEY",
  "model": "your-model-id"
}
```

Set the model and URL to those of your service. Importing JSON only fills the settings; enter the key separately, or provide it through the environment variable named by `api_key_env` in the JSON. **Save settings** retains the URL, model and proxy in the app's local preferences and stores a supplied key in macOS Keychain under that base URL. On later launches, the saved service and key are reused; leave the key field blank to keep the existing key, or enter a replacement and save. The key is never written to Provider JSON or the repository. Temporary provider configuration files contain no key and are deleted after use. A local gateway may still forward requests to a remote upstream: the final destination depends on its channel configuration. Review, QA and export in an existing local session do not require an API connection.

Choose **Translate and open Workbench**. The app runs format preflight, translation proposals, deterministic QA and semantic adjudication, then opens the generated review session only at `READY_FOR_HUMAN_REVIEW`. Quotation marks and workflow arrows do not exempt ordinary words from translation. For Chinese-to-English work, QA marks unapproved residual Chinese as an `UNTRANSLATED_SOURCE_TEXT` error; correct the target and rerun QA before final export. A configured **Draft** export replaces all aligned source units with their approved or suggested translation in a new document of the original format, even when decisions are still pending. The receipt lists those pending units. **Final** requires review decisions and fresh QA. Both produce a receipt, bilingual HTML and Agent handoff beside the native file. See [format support](DOCUMENT_FORMATS.md) for fidelity and dependencies.

## Upload documents from the home screen

If you already have a translation or want to start a local review session, choose **Local bilingual review** from Welcome. This separate screen accepts a source and an optional existing target. When you supply a target, check segment order and confirm alignment. **Upload documents and open Workbench** inspects the files, creates a new `.dbreview` session and opens it directly. A source-only upload retains source text as an unreviewed working copy; it does not call the API or generate translations. **Open demo** and **Continue work** are available on this screen; the demo is not required for uploads.

## Open a saved session or review offline

Choose **Open .dbreview session** and select the session directory, or **Open demo**. A session created by the runtime reconnects its original source from `run.json` when that source still exists. Upload-created sessions retain their source copy in `inputs/`. The menu bar's **File → Open in Browser** opens the same local session with its current token if you prefer a full browser window.

In the Workbench, compare source and target with original line breaks, repeated spaces and indentation visible. The three primary decisions are **Accept Translation**, **Edit Translation** and **Reject Translation**. Rejection requires a reason and creates a record in the left-hand **Rejection Memory** view. Later proposals for the same source and language pair cannot repeat that wording; short source phrases also match inside longer segments. Records can be removed there. **Accept all pending suggestions** applies only to unreviewed units with suggestions and rechecks each decision. Run fresh QA before native delivery or export a review snapshot.

Decisions and notes are saved immediately in the `.dbreview` directory with a backup; the selected unit, page and view are restored when reopening. **Save progress** writes the selected unit, view, unapproved translation edit and review-note draft to the local `.dbreview` session and its backup. Leaving with new edits offers **Save and Leave** (the default), **Discard New Edits**, or **Cancel**; a successful save returns to Welcome. Reopening restores those drafts without treating them as approved translations. The divider between segments and the inspector can be dragged; the export controls above follow the same boundary. Recent sessions can be resumed from the local review screen, and **New parallel task window** can open another task in a separate app instance. One session cannot be opened for editing in two instances at once. Chat occupies the lower right inspector, can collapse or resize, and can quote the current source and target, ask why a proposal was made, accept a typed follow-up, or attach a document or image. Chat requires a configured API service and sends the attached content to that service; the conversation is saved inside the session. Saving API settings while a Workbench is already open connects that session's chat without restarting it. **Search in browser** opens the current selection, question or source text with the macOS default browser. Chat responses and search results are research aids, not review decisions or verified evidence. The native window uses a macOS Save panel for downloaded files. Closing the app stops its local server; reopening the saved `.dbreview` directory resumes the review. The installed app copies its demo once to `~/Library/Application Support/DBabel/local-demo.dbreview` and preserves later decisions; the source build uses `output/local-demo.dbreview`.

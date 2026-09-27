# DBabel for macOS

[简体中文](DESKTOP_APP.zh-CN.md) · [Documentation index](INDEX.md)

The macOS app opens the existing Full Local Review Workbench in a native window. It can run a translation project through the current provider runtime, open an existing `.dbreview` session, or open a separate demo copy. Review decisions remain in the session directory. The app does not approve translations automatically.

## Install and open

The packaged Apple Silicon disk image is `output/release/DBabel-macOS-AppleSilicon.dmg`. Open it, drag **DBabel.app** to Applications, then launch it. The app bundles Python 3.12, OpenSSL 3 and its runtime dependencies. Demo and new sessions are written to `~/Library/Application Support/DBabel/`; the installed app does not depend on the checkout or `.venv`. This local build is ad-hoc signed and not notarized; a public Developer ID distribution has not been prepared.

To rebuild the disk image from source, use macOS on Apple Silicon with Xcode Command Line Tools and network access for the first dependency download:

```bash
cd /path/to/DBabel
sh scripts/package_macos_app.sh
open output/release/DBabel-macOS-AppleSilicon.dmg
```

For development, `sh scripts/build_macos_app.sh` produces a checkout-bound `output/desktop/DBabel.app`. It uses the prepared `output/build-python` and `output/build-vendor` runtime when present, then falls back to a repository `.venv`. The Swift-only build does not install Python dependencies; run `sh scripts/package_macos_app.sh` to prepare a self-contained build, or install `requirements-dev.txt` into `.venv` before launching the development app. The Python browser launcher remains available on macOS, Windows and Linux through `python scripts/start_local.py`.

The home screen and embedded Workbench share one macOS window material. The three controls at the top right are **Home**, **Appearance**, and **Language**. Appearance offers Follow System, Light, and Dark; the globe toggles English and Simplified Chinese. The network icon on the left opens **API service settings** from either the home screen or the Workbench. The Workbench uses WebKit's optional, non-public canvas switch to reveal the window material; a distributable App Store build needs this compatibility choice reviewed or replaced.

## Translate a document

Choose a DOCX, TXT, Markdown or XLSX source. Select distinct source and target languages from the menus, such as `zh-CN` and `en`, and enter a concrete text role such as `PROSE`. Select **Configure API service** and enter the base URL from your service's documentation, a model ID available to your account, and a key issued by that service. The app uses OpenAI-compatible Chat Completions and appends `/chat/completions` to the base URL, so do not include that path in the URL field. Remote services require HTTPS; a local service can use a URL such as `http://127.0.0.1:8000/v1`. For a gateway, enter its user token rather than the key it uses to connect to an upstream channel.

The model must be enabled by the chosen service, accessible to the key, and support Chat Completions. **Test model connection** sends one short request through the same code path used by translation, checking the URL, key, model route and response shape; it may incur a small amount of API usage. If a gateway forwards requests, check its upstream channel, model mapping and quota.

The connection test checks only the API; it does not parse the selected document. **Translate and open Workbench** starts format preflight, extraction and translation. XLSX uses the built-in extractor for stored text cells; pure numbers, dates, booleans and formulas remain untouched and are not sent as translation units. More text cells mean more translation and semantic-review requests. If the run stops, the home screen shows its stage and reason. A small document is useful for checking the workflow before spending a limited balance on a full workbook.

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

Choose **Translate and open Workbench**. The app runs format preflight, translation proposals, deterministic QA and semantic adjudication, then opens the generated review session only at `READY_FOR_HUMAN_REVIEW`. The Workbench retains explicit human decisions. A configured native export creates a reviewed copy beside the runtime session, plus a receipt, bilingual HTML and Agent handoff. See [format support](DOCUMENT_FORMATS.md) for fidelity and dependencies.

## Upload documents from the home screen

If you already have a translation or want to start a local review session, select the source on the home screen, then use **Upload documents for review**. An existing target is optional. When you supply one, check the source/target segment order and confirm alignment. **Upload documents and open Workbench** inspects the files, creates a new `.dbreview` session and opens it directly. A source-only upload retains source text as an unreviewed working copy; it does not call the API or generate translations. **Open demo** is for exploring sample data and is not required for uploads.

## Open a saved session or review offline

Choose **Open .dbreview session** and select the session directory, or **Open demo**. A session created by the runtime reconnects its original source from `run.json` when that source still exists. Upload-created sessions retain their source copy in `inputs/`. The menu bar's **File → Open in Browser** opens the same local session with its current token if you prefer a full browser window.

In the Workbench, compare source and target, record decisions, run fresh QA, then export a review snapshot or native delivery. The native window uses a macOS Save panel for downloaded files. Closing the app stops its local server; reopening the saved `.dbreview` directory resumes the review. The installed app copies its demo once to `~/Library/Application Support/DBabel/local-demo.dbreview` and preserves later decisions; the source build uses `output/local-demo.dbreview`.

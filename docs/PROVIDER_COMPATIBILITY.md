# API compatibility and recovery

[中文说明](PROVIDER_COMPATIBILITY.zh-CN.md)

Choose the protocol supplied by your gateway: **Chat Completions** for NewAPI/OpenAI-compatible channels, **Responses** for `/responses`, or **Claude Messages** for the native Anthropic API. Base URLs and complete endpoint URLs are accepted; DBabel does not append a second endpoint. Keep the gateway's exact model name. A successful connection test does not prove a complete document run.

For a company NewAPI gateway, connect to its required intranet/VPN first. Start with streaming enabled and a 300-second idle timeout. Keep the system proxy, or select direct mode if company policy routes intranet traffic directly. A trusted HTTP intranet endpoint requires the existing explicit HTTP opt-in; TLS verification remains enabled. The app does not whitelist vendors/models. No company endpoint or credential is bundled.

Desktop settings expose protocol, **Request client** (Automatic, Built-in compatible client, Official SDK), streaming, omission of temperature, timeout (1–600 seconds), and an optional model-parameters JSON object. Imported provider files also support `max_output_tokens` and `transport_backend`. Model parameters, for example `{"thinking":{"type":"disabled"}}`, are passed only when the user supplies them; support depends on the gateway/model. Do not place credentials in this object. GPT/o-series reasoning models omit sampling temperature by default. A 400 response explicitly rejecting temperature or streaming triggers one fallback removing that field. Other 400 responses remain visible errors.

JSON and SSE responses are normalized into final text. SSE comments, multiline data, CR/LF/CRLF, usage frames and finish markers are handled; reasoning text and tool calls never substitute for a translation. Incomplete UTF-8/JSON, truncated streams, output-token exhaustion, idle timeouts and empty final answers cannot become completed checkpoints. Stream buffering is bounded by the configured response-size limit, with a total deadline of `max(600, timeout_seconds * 6)` seconds.

Transport attempts are bounded to three, with backoff and a Retry-After delay capped at 60 seconds. Authentication/permission/quota failures (401/403/402) stop immediately. An interrupted multi-unit translation or semantic batch is halved, and later batches use the smaller size. Contract errors get focused retries; completed batches stay saved. Resume may change timeout, streaming, proxy, temperature or model options without repeating completed work; source, languages, endpoint, model and protocol identity must still match. Previously completed text is intentionally not regenerated under new options.

## Optional maintained SDK transport and task probe

Install [requirements-integration.txt](../requirements-integration.txt) for pinned OpenAI/Anthropic SDK adapters. `transport_backend` accepts `auto` (use an installed compatible SDK, otherwise the standard-library transport), `stdlib`, or `sdk` (report unavailable rather than silently switch). SDKs require Python 3.10+; the core transport remains available on Python 3.9. DBabel still owns response completion, bounded retry, checkpoint and human-review semantics. [Third-party notices](../THIRD_PARTY_NOTICE.md) credit the adopted SDKs and preserve their original licenses.

**Request client** defaults to Automatic (`auto`). Select Built-in compatible client (`stdlib`) when testing a gateway with the original standard-library adapter, or Official SDK (`sdk`) to require the installed SDK adapter. This choice is saved, retained on configuration import and passed to translation runs; changing the client keeps the same service identity for checkpoint resume.

The Anthropic SDK adapter requires an endpoint ending in `/v1/messages`; `auto` uses the standard-library transport for other Messages paths. SDK retries are disabled so DBabel owns the retry limit. Model-parameter extensions stay in the JSON request body and cannot override SDK transport headers or timeout settings.

SDK requests send `Accept-Encoding: identity`. A compressed response is rejected before decoding so the response-size limit also bounds SDK error bodies. Configure the gateway to honor identity encoding; the current SDK adapter does not decompress gzip, Brotli or other encoded responses. Transport diagnostics include SDK/version, request ID, timing and received bytes, with configured credentials redacted.

```bash
python scripts/check_provider_connection.py --provider-config provider.json --task-check
```

This command sends one small synthetic Chinese-to-English translation, verifies the requested JSON unit and protected literals, and returns `TASK_READY` or `CONTRACT_FAILED` with usage/transport diagnostics. It uses provider tokens and measures one contract, not document-wide quality or throughput. Plain connection availability, format preflight, successful ingestion, actual coverage and final export remain separate checks.

The desktop **Test translation capability** button runs this task probe. Its result distinguishes a usable translation contract from a connected endpoint that returned an invalid contract, with the validation failures shown for correction.

## Reviewed upstream references

Reviewed on 2026-10-03: [OpenAI Python SSE decoder](https://github.com/openai/openai-python/blob/main/src/openai/_streaming.py) (event framing, heartbeats and termination), [OpenAI retry handling](https://github.com/openai/openai-python/blob/main/src/openai/_base_client.py) (transient status classes and bounded delay), and [NewAPI OpenAI adaptor](https://github.com/QuantumNous/new-api/blob/main/relay/channel/openai/adaptor.go) (channel-specific request/stream conversion). These are implementation references, not proof that every company channel behaves identically. DBabel's standard-library adapter remains independently implemented; upstream implementation files and a NewAPI server are not copied into it. Optional SDK adapters use the installed maintained libraries through their public APIs.

The regression suite uses local synthetic gateways and exercises streaming frames, rate limits, terminal errors, native protocol payloads, smaller batches and transport changes during resume. Real company-network testing remains necessary for company-specific token policy, timeout, model names and supported extensions.

## Portable Review

Portable HTML remains self-contained with network access disabled and needs no API account. It caches decisions, current selection and pending text/note drafts in browser local storage, bound to session and original unit text; mismatched inputs are not restored. Browser cleanup, private mode or storage failure can erase/prevent that cache. **Save progress** downloads a recovery JSON containing decisions and unfinished drafts; **Restore progress** restores it only into the matching session. **Export decisions.json** remains the interoperable decision-only file; unfinished drafts never become approved decisions. Export/import decisions into the matching Full Local Workbench and rerun QA for original-format delivery. Native document export and AI chat are Full Local features.

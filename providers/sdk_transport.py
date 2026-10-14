"""Optional official SDK transports with DBabel-owned completion validation."""
from __future__ import annotations

import importlib.util
import json
import time
from urllib.parse import urlparse
from urllib.request import proxy_bypass

from providers.base import ProviderError, ProviderTransientError, ProviderResponseInterrupted
from providers.errors import exception_chain, safe_text, service_message, service_request_id


def available(mode):
    name = "anthropic" if mode == "anthropic_messages" else "openai"
    return importlib.util.find_spec(name) is not None and importlib.util.find_spec("httpx2") is not None


def compatible(endpoint, mode):
    return mode != "anthropic_messages" or endpoint.endswith("/v1/messages")


def terminal(line):
    if line.strip() == b"data: [DONE]":
        return True
    if line.startswith(b"data:"):
        try:
            value = json.loads(line[5:].strip())
            return value.get("type") in {"response.completed", "response.failed", "response.incomplete", "message_stop"}
        except (ValueError, AttributeError):
            pass
    return False


def request(endpoint, headers, body, timeout, max_bytes, *, config, on_progress=None, cancel_event=None):
    import httpx2
    mode = config.api_mode
    payload = json.loads(body)
    suffix = {"chat_completions": "/chat/completions", "responses": "/responses",
              "anthropic_messages": "/v1/messages"}[mode]
    base = endpoint[:-len(suffix)]
    parsed = urlparse(endpoint)
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    system_bypass = (not local and config.proxy_mode == "system"
                     and proxy_bypass(parsed.netloc))
    # HTTPX reads the platform's proxy URLs but omits macOS proxy exceptions.
    # Resolve this destination with urllib, as the standard-library path does.
    # A direct transport disables HTTPX proxy mounts while retaining environment
    # CA settings needed by enterprise HTTPS services.
    direct_transport = httpx2.HTTPTransport(trust_env=True) if system_bypass else None
    route = ("DIRECT_LOCAL" if local else "DIRECT_CONFIGURED" if config.proxy_mode == "none"
             else "DIRECT_SYSTEM_BYPASS" if system_bypass else "CUSTOM" if config.proxy_mode == "custom"
             else "SYSTEM")
    class LimitedStream(httpx2.SyncByteStream):
        def __init__(self, stream):
            self.stream = stream
        def __iter__(self):
            size = 0
            for part in self.stream:
                size += len(part)
                if size > max_bytes:
                    raise ProviderError("provider response exceeded configured size limit")
                yield part
        def close(self):
            self.stream.close()
    def bounded(response):
        if response.headers.get("content-encoding", "identity").lower() not in {"", "identity"}:
            response.close()
            raise ProviderError("provider returned compressed content despite identity encoding; use an identity-compatible gateway")
        length = response.headers.get("content-length")
        if length and length.isdigit() and int(length) > max_bytes:
            response.close()
            raise ProviderError("provider response exceeded configured size limit")
        # Bound error bodies too: SDKs read them before raising APIStatusError.
        response.stream = LimitedStream(response.stream)
    http_client = httpx2.Client(trust_env=not local and config.proxy_mode != "none",
                               transport=direct_transport,
                               follow_redirects=False, timeout=float(timeout),
                               headers={"Accept-Encoding": "identity"},
                               event_hooks={"response": [bounded]})
    if mode == "anthropic_messages":
        import anthropic as sdk
        client = sdk.Anthropic(api_key=headers["x-api-key"], base_url=base,
                               http_client=http_client, max_retries=0)
        create = client.messages.with_streaming_response.create
    else:
        import openai as sdk
        client = sdk.OpenAI(api_key=headers["Authorization"][7:], base_url=base,
                            http_client=http_client, max_retries=0)
        create = (client.chat.completions.with_streaming_response.create if mode == "chat_completions"
                  else client.responses.with_streaming_response.create)
    core = {"model", "messages", "system", "input", "instructions", "store", "stream",
            "temperature", "max_tokens", "max_completion_tokens", "max_output_tokens"}
    import inspect
    core.intersection_update(inspect.signature(create).parameters)
    direct = {key: value for key, value in payload.items() if key in core}
    extras = {key: value for key, value in payload.items() if key not in core}
    started = time.monotonic()
    records = {"backend": "sdk", "sdk": sdk.__name__, "sdk_version": sdk.__version__,
               "route": route}
    credentials = tuple(value for value in (headers.get("x-api-key"), headers.get("Authorization"),
        headers.get("Authorization", "").removeprefix("Bearer ")) if value)
    def failure_details(exc):
        original = next((str(item) for item in reversed(exception_chain(exc)) if str(item)), str(exc))
        return {**records, "service_message": safe_text(original, credentials)}
    def check_cancel():
        if cancel_event is not None and cancel_event.is_set():
            raise ProviderError("provider request cancelled")
        if time.monotonic() - started > max(600, timeout * 6):
            raise ProviderResponseInterrupted("provider stream exceeded total request deadline")
    try:
        check_cancel()
        with create(**direct, extra_body=extras or None) as response:
            records["headers_ms"] = round((time.monotonic() - started) * 1000)
            request_id = response.headers.get("x-request-id") or response.headers.get("request-id")
            if request_id:
                for credential in (headers.get("x-api-key"), headers.get("Authorization"),
                                   headers.get("Authorization", "").removeprefix("Bearer ")):
                    if credential:
                        request_id = request_id.replace(credential, "[redacted]")
            records["request_id"] = request_id[:128] if request_id else None
            stream = "text/event-stream" in response.headers.get("content-type", "").lower()
            if on_progress:
                on_progress({"stage": "PROVIDER", "state": "RESPONSE_STARTED"})
            chunks, size, tail = [], 0, b""
            for chunk in response.iter_bytes():
                check_cancel()
                size += len(chunk)
                if size > max_bytes:
                    raise ProviderError("provider response exceeded configured size limit")
                if "first_byte_ms" not in records:
                    records["first_byte_ms"] = round((time.monotonic() - started) * 1000)
                chunks.append(chunk)
                if on_progress:
                    on_progress({"stage": "PROVIDER", "state": "RECEIVING", "received_bytes": size})
                if stream:
                    tail += chunk
                    lines = tail.split(b"\n")
                    tail = lines.pop()
                    if any(terminal(line.rstrip(b"\r")) for line in lines):
                        break
            raw = b"".join(chunks)
            records["elapsed_ms"] = round((time.monotonic() - started) * 1000)
            records["response_bytes"] = size
            return response.status_code, raw, records
    except sdk.APIStatusError as exc:
        status = exc.status_code
        error = ProviderResponseInterrupted if status in {408, 504} else ProviderTransientError if status in {409, 425, 429} or status >= 500 else ProviderError
        try:
            retry_after = min(60, max(0, float(exc.response.headers.get("retry-after", 0))))
        except (TypeError, ValueError):
            retry_after = None
        detail = safe_text(service_message(exc.body) or str(exc), credentials)
        request_id = service_request_id(exc.response.content, exc.response.headers)
        guidance = {401: "API key or gateway token was rejected", 403: "token lacks access to this model",
                    402: "service balance or quota is exhausted", 429: "quota or rate limit was reached"}.get(status, "service returned an error")
        raise error("provider HTTP error: {} ({}; {})".format(status, guidance, detail[:350]),
                    status=status, retry_after=retry_after,
                    details={**records, "service_message": detail, "request_id": safe_text(request_id, credentials, 128)},
                    secrets=credentials) from exc
    except (sdk.APITimeoutError, httpx2.TimeoutException) as exc:
        raise ProviderResponseInterrupted("provider SDK request timed out", details=failure_details(exc), secrets=credentials) from exc
    except httpx2.RemoteProtocolError as exc:
        raise ProviderResponseInterrupted("provider SDK response disconnected before completion", details=failure_details(exc), secrets=credentials) from exc
    except (sdk.APIConnectionError, httpx2.HTTPError) as exc:
        cause = exc.__cause__
        while cause is not None:
            if isinstance(cause, ProviderError):
                cause.details = {**records, **cause.details}
                cause._secrets += credentials
                raise cause from exc
            cause = cause.__cause__
        raise ProviderTransientError("provider SDK connection failed; check VPN/proxy and the endpoint",
            details=failure_details(exc), secrets=credentials) from exc
    except ProviderError as exc:
        exc.details = {**records, **exc.details}
        exc._secrets += credentials
        raise
    finally:
        client.close()

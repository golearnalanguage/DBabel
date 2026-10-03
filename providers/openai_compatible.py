from __future__ import annotations

import json
import re
import time
import socket
from http.client import IncompleteRead, RemoteDisconnected
from typing import Callable, Mapping, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import (
    HTTPRedirectHandler,
    ProxyHandler,
    Request,
    build_opener,
)

from providers.base import (
    ProviderError,
    ProviderTransientError,
    ProviderResponseInterrupted,
    TextGenerationProvider,
)
from runtime.models import (
    GenerationRequest,
    GenerationResponse,
    ProviderConfig,
)
from providers.protocol import decode_response

Transport = Callable[
    [str, Mapping[str, str], bytes, int, int],
    Tuple[int, bytes],
]


def _completion_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict)
            and part.get("type") in {"text", "output_text"}
            and isinstance(part.get("text"), str)
        )
    return None

_LOCAL_HOSTS = {
    "localhost",
    "127.0.0.1",
    "::1",
}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self,
        req,
        fp,
        code,
        msg,
        headers,
        newurl,
    ):
        return None


def _build_transport_opener(
    url: str,
    proxy_mode: str = "system",
):
    hostname = (
        urlparse(url).hostname
        or ""
    )

    # Local model/provider traffic must never be sent
    # through an ambient HTTP(S) proxy. This matters
    # for localhost OpenAI-compatible servers, Ollama,
    # and packaged desktop integrations.
    if hostname in _LOCAL_HOSTS or proxy_mode == "none":
        return build_opener(
            ProxyHandler({}),
            _NoRedirect,
        )

    # Remote providers retain the platform/environment
    # proxy behaviour supplied by urllib.
    return build_opener(
        _NoRedirect
    )


def _default_transport(
    url: str,
    headers: Mapping[str, str],
    body: bytes,
    timeout: int,
    max_response_bytes: int,
    proxy_mode: str = "system",
) -> Tuple[int, bytes]:
    request = Request(
        url,
        data=body,
        headers=dict(headers),
        method="POST",
    )

    opener = _build_transport_opener(
        url, proxy_mode
    )

    try:
        with opener.open(
            request,
            timeout=timeout,
        ) as response:
            is_stream = "text/event-stream" in response.headers.get("Content-Type", "").lower()
            if is_stream:
                chunks, size = [], 0
                started = time.monotonic()
                while True:
                    line = response.readline(max_response_bytes + 1 - size)
                    if not line:
                        break
                    size += len(line)
                    chunks.append(line)
                    if size > max_response_bytes:
                        raise ProviderError("provider response exceeded configured size limit")
                    # Stop at the service's terminal marker even if its keep-alive
                    # socket remains open. Heartbeats reset the read idle timeout.
                    if line.strip() == b"data: [DONE]":
                        break
                    if line.startswith(b"data:"):
                        try:
                            event = json.loads(line[5:].strip())
                            if event.get("type") in {"response.completed", "response.failed", "response.incomplete", "message_stop"}:
                                break
                        except (ValueError, AttributeError):
                            pass
                    if time.monotonic() - started > max(600, timeout * 6):
                        raise ProviderResponseInterrupted("provider stream exceeded total request deadline")
                raw = b"".join(chunks)
            else:
                raw = response.read(max_response_bytes + 1)

            if len(raw) > max_response_bytes:
                raise ProviderError(
                    "provider response exceeded "
                    "configured size limit"
                )

            declared_length = response.headers.get("Content-Length")
            if declared_length is not None and not is_stream:
                try:
                    expected_length = int(declared_length)
                except ValueError:
                    expected_length = None
                if expected_length is not None and len(raw) < expected_length:
                    raise ProviderResponseInterrupted(
                        "provider response ended before its declared length"
                    )

            return int(response.status), raw

    except HTTPError as exc:
        guidance = {
            400: "request or model was rejected",
            401: "API key or gateway token was rejected",
            402: "service balance or quota is exhausted; saved progress can be resumed after refill",
            403: "token lacks access to this model",
            404: "API route or model was not found",
            429: "quota or rate limit was reached",
        }.get(exc.code, "service returned an error")
        detail = ""
        try:
            payload = json.loads(exc.read(4096).decode("utf-8"))
            issue = payload.get("error", payload) if isinstance(payload, dict) else {}
            if isinstance(issue, dict):
                detail = str(issue.get("message") or issue.get("code") or "")[:350]
        except (ValueError, UnicodeDecodeError, OSError):
            pass
        finally:
            exc.close()
        if detail:
            for name in ("Authorization", "x-api-key"):
                if headers.get(name):
                    detail = detail.replace(headers[name], "[redacted]")
            detail = re.sub(r"(?i)(bearer\s+|sk-)[A-Za-z0-9_-]{12,}", "[redacted]", detail)
            guidance += "; " + detail
        error_type = (ProviderResponseInterrupted if exc.code in {408, 504} else
                      ProviderTransientError if exc.code in {409, 425, 429} or 500 <= exc.code <= 599 else ProviderError)
        try:
            retry_after = min(60, max(0, float(exc.headers.get("Retry-After", "0"))))
        except (TypeError, ValueError):
            retry_after = None
        raise error_type(
            "provider HTTP error: {} ({})".format(exc.code, guidance),
            status=exc.code, retry_after=retry_after,
        ) from exc

    except (IncompleteRead, RemoteDisconnected) as exc:
        raise ProviderResponseInterrupted(
            "provider response ended before it was complete"
        ) from exc

    except URLError as exc:
        reason = str(exc.reason)
        if isinstance(exc.reason, (TimeoutError, socket.timeout)) or "timed out" in reason.lower():
            raise ProviderResponseInterrupted("provider read timed out; retrying with smaller work batches is supported") from exc
        if any(marker in reason.lower() for marker in (
            "ssl", "tls", "connection reset", "eof occurred"
        )):
            raise ProviderTransientError(
                "provider TLS/network connection failed before key or model "
                "validation; check VPN and proxy settings: {}".format(reason)
            ) from exc
        raise ProviderTransientError(
            "provider connection error: {}".format(
                reason
            )
        ) from exc

    except (TimeoutError, socket.timeout) as exc:
        raise ProviderResponseInterrupted("provider read timed out; no completed batch was lost") from exc
    except OSError as exc:
        raise ProviderTransientError(
            "provider I/O error: {}".format(exc)
        ) from exc


class OpenAICompatibleProvider(
    TextGenerationProvider
):
    def __init__(
        self,
        config: ProviderConfig,
        environ: Optional[Mapping[str, str]] = None,
        transport: Optional[Transport] = None,
    ):
        config.validate()

        self._config = config
        self._api_key = config.resolve_api_key(
            environ
        )
        self._transport = (
            transport or (lambda url, headers, body, timeout, max_bytes:
                _default_transport(url, headers, body, timeout, max_bytes,
                                   config.proxy_mode))
        )

    @property
    def config(self) -> ProviderConfig:
        return self._config

    def _payload(self, request):
        config = self._config
        mode = config.api_mode
        suffix = {"chat_completions": "/chat/completions", "responses": "/responses",
                  "anthropic_messages": "/messages"}[mode]
        base = config.base_url.rstrip("/")
        endpoint = base if base.endswith(suffix) else base + suffix
        reasoning = config.model.lower().startswith(("gpt-5", "gpt-6", "o1", "o3", "o4"))
        content = request.user
        if request.images:
            content = [{"type": "text", "text": request.user}] + [
                {"type": "image_url", "image_url": {"url": image}} for image in request.images]
        payload = {"model": config.model, "stream": config.stream}
        if mode == "chat_completions":
            payload["messages"] = [{"role": "system", "content": request.system},
                                   {"role": "user", "content": content}]
            if config.max_output_tokens:
                payload["max_completion_tokens" if reasoning else "max_tokens"] = config.max_output_tokens
        elif mode == "responses":
            if request.images:
                content = [{"type": "input_text", "text": request.user}] + [
                    {"type": "input_image", "image_url": image} for image in request.images]
            payload.update(instructions=request.system, input=[{"role": "user", "content": content}], store=False)
            if config.max_output_tokens:
                payload["max_output_tokens"] = config.max_output_tokens
        else:
            if request.images:
                content = [{"type": "text", "text": request.user}]
                for image in request.images:
                    prefix, data = image.split(",", 1)
                    content.append({"type": "image", "source": {"type": "base64",
                                    "media_type": prefix[5:].split(";")[0], "data": data}})
            payload.update(system=request.system, messages=[{"role": "user", "content": content}],
                           max_tokens=config.max_output_tokens or 8192)
        if config.temperature_mode == "auto" and not reasoning:
            payload["temperature"] = float(request.temperature)
        payload.update(config.extra_body)
        return endpoint, payload

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        request.validate()
        endpoint, payload = self._payload(request)
        headers = {"Authorization": "Bearer " + self._api_key,
                   "Content-Type": "application/json",
                   "Accept": "text/event-stream, application/json",
                   "User-Agent": "DBabel-Runtime/1.6"}
        if self._config.api_mode == "anthropic_messages":
            headers.pop("Authorization")
            headers.update({"x-api-key": self._api_key, "anthropic-version": "2023-06-01"})
        attempts = 0
        while True:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            try:
                status, raw = self._transport(endpoint, headers, body,
                    self._config.timeout_seconds, self._config.max_response_bytes)
                if not 200 <= int(status) < 300:
                    error_type = ProviderResponseInterrupted if status in {408, 504} else ProviderTransientError if status in {409, 425, 429} or status >= 500 else ProviderError
                    raise error_type("provider returned HTTP status: " + str(status), status=status)
                if len(raw) > self._config.max_response_bytes:
                    raise ProviderError("provider response exceeded configured size limit")
                try:
                    data = decode_response(raw, self._config.api_mode)
                except (AttributeError, TypeError, KeyError) as exc:
                    raise ProviderError("provider returned an invalid protocol structure") from exc
                try:
                    choice = data["choices"][0]
                    message = choice["message"]
                    text = _completion_text(message.get("content"))
                except (KeyError, IndexError, TypeError) as exc:
                    raise ProviderError("provider response is missing choices[0].message.content") from exc
                if choice.get("finish_reason") in {"length", "max_tokens"}:
                    raise ProviderResponseInterrupted("provider exhausted output tokens before completing the answer")
                if choice.get("finish_reason") in {"content_filter", "refusal", "tool_calls", "tool_use"} or message.get("refusal"):
                    raise ProviderError("provider did not return a text answer: " + str(choice.get("finish_reason")))
                if not isinstance(text, str) or not text.strip():
                    raise ProviderResponseInterrupted("provider returned no final answer; reasoning text is not a translation")
                return GenerationResponse(text=text, model=data.get("model") or self._config.model,
                    provider=self._config.provider, response_id=data.get("id"),
                    usage=data.get("usage") if isinstance(data.get("usage"), dict) else {})
            except (IncompleteRead, RemoteDisconnected, TimeoutError, socket.timeout) as exc:
                transient = ProviderResponseInterrupted("provider response disconnected or timed out")
                transient.__cause__ = exc
            except ProviderTransientError as exc:
                transient = exc
            except ProviderError as exc:
                safe = str(exc).replace(self._api_key, "[redacted]")
                # Some gateways reject optional sampling/stream fields. Only
                # remove a field explicitly named in a 400 rejection, once.
                if exc.status == 400 and any(word in safe.lower() for word in
                        ("unsupported", "not supported", "not allowed", "unknown", "invalid")):
                    if "temperature" in safe.lower() and "temperature" in payload:
                        payload.pop("temperature")
                        continue
                    if "stream" in safe.lower() and payload.get("stream"):
                        payload["stream"] = False
                        continue
                raise ProviderError(safe, status=exc.status) from exc
            if attempts >= 2:
                raise type(transient)("provider request failed after 3 attempts: " +
                    str(transient).replace(self._api_key, "[redacted]"),
                    status=transient.status, retry_after=transient.retry_after) from transient
            delay = transient.retry_after or (0.5 * (2 ** attempts))
            time.sleep(min(60, delay))
            attempts += 1

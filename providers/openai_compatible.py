from __future__ import annotations

import json
import re
import time
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
            raw = response.read(
                max_response_bytes + 1
            )

            if len(raw) > max_response_bytes:
                raise ProviderError(
                    "provider response exceeded "
                    "configured size limit"
                )

            declared_length = response.headers.get("Content-Length")
            if declared_length is not None:
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
        if detail:
            detail = detail.replace(headers.get("Authorization", ""), "[redacted]")
            detail = re.sub(r"(?i)(bearer\s+|sk-)[A-Za-z0-9_-]{12,}", "[redacted]", detail)
            guidance += "; " + detail
        error_type = ProviderTransientError if exc.code in {408, 425, 429} or 500 <= exc.code <= 599 else ProviderError
        raise error_type(
            "provider HTTP error: {} ({})".format(exc.code, guidance)
        ) from exc

    except (IncompleteRead, RemoteDisconnected) as exc:
        raise ProviderResponseInterrupted(
            "provider response ended before it was complete"
        ) from exc

    except URLError as exc:
        reason = str(exc.reason)
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

    def generate(
        self,
        request: GenerationRequest,
    ) -> GenerationResponse:
        request.validate()

        endpoint = (
            self._config.base_url.rstrip("/")
            + "/chat/completions"
        )

        user_content = request.user
        if request.images:
            user_content = [{"type": "text", "text": request.user}] + [
                {"type": "image_url", "image_url": {"url": image}}
                for image in request.images
            ]
        payload = {
            "model": self._config.model,
            "messages": [
                {
                    "role": "system",
                    "content": request.system,
                },
                {
                    "role": "user",
                    "content": user_content,
                },
            ],
            "stream": False,
        }
        # Reasoning models exposed directly or through New API can reject
        # temperature unless reasoning is disabled. These model families use
        # the service default; other compatible models retain the requested
        # sampling setting.
        reasoning_prefixes = (
            "gpt-5", "gpt-6", "o1", "o3", "o4"
        )
        if not self._config.model.lower().startswith(reasoning_prefixes):
            payload["temperature"] = float(request.temperature)

        body = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

        headers = {
            "Authorization":
                "Bearer " + self._api_key,
            "Content-Type":
                "application/json",
            "Accept":
                "application/json",
            "User-Agent":
                "DBabel-Runtime/0.1",
        }

        for attempt in range(3):
            try:
                status, raw = self._transport(
                    endpoint,
                    headers,
                    body,
                    self._config.timeout_seconds,
                    self._config.max_response_bytes,
                )
                if 200 <= int(status) < 300:
                    try:
                        preview = json.loads(raw.decode("utf-8"))
                        choice = preview["choices"][0]
                        message = choice["message"]
                        content = _completion_text(message.get("content"))
                        if choice.get("finish_reason") == "length" or (
                            not content and message.get("reasoning_content")
                        ):
                            raise ProviderResponseInterrupted(
                                "provider ended before producing a complete answer"
                            )
                    except (UnicodeDecodeError, ValueError, KeyError, IndexError, TypeError):
                        pass
                break
            except (IncompleteRead, RemoteDisconnected) as exc:
                transient = ProviderResponseInterrupted(
                    "provider response ended before it was complete"
                )
                transient.__cause__ = exc
            except ProviderTransientError as exc:
                transient = exc
            if attempt == 2:
                raise type(transient)(
                    "provider request failed after 3 attempts: {}".format(transient)
                ) from transient
            time.sleep(0.5 * (2 ** attempt))

        if not 200 <= int(status) < 300:
            raise ProviderError(
                "provider returned unexpected "
                "HTTP status: {}".format(status)
            )

        if (
            len(raw)
            > self._config.max_response_bytes
        ):
            raise ProviderError(
                "provider response exceeded "
                "configured size limit"
            )

        try:
            data = json.loads(
                raw.decode("utf-8")
            )
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise ProviderError(
                "provider returned invalid "
                "UTF-8 JSON"
            ) from exc

        try:
            text = _completion_text(data["choices"][0]["message"]["content"])
        except (
            KeyError,
            IndexError,
            TypeError,
        ) as exc:
            raise ProviderError(
                "provider response is missing "
                "choices[0].message.content"
            ) from exc

        if (
            not isinstance(text, str)
            or not text.strip()
        ):
            raise ProviderError(
                "provider returned an empty "
                "or non-text completion"
            )

        usage = (
            data.get("usage")
            if isinstance(
                data.get("usage"),
                dict,
            )
            else {}
        )

        response_id = (
            data.get("id")
            if isinstance(
                data.get("id"),
                str,
            )
            else None
        )

        model = (
            data.get("model")
            if isinstance(
                data.get("model"),
                str,
            )
            else self._config.model
        )

        return GenerationResponse(
            text=text,
            model=model,
            provider=self._config.provider,
            response_id=response_id,
            usage=usage,
        )

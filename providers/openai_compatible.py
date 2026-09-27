from __future__ import annotations

import json
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
):
    hostname = (
        urlparse(url).hostname
        or ""
    )

    # Local model/provider traffic must never be sent
    # through an ambient HTTP(S) proxy. This matters
    # for localhost OpenAI-compatible servers, Ollama,
    # and packaged desktop integrations.
    if hostname in _LOCAL_HOSTS:
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
) -> Tuple[int, bytes]:
    request = Request(
        url,
        data=body,
        headers=dict(headers),
        method="POST",
    )

    opener = _build_transport_opener(
        url
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

            return int(response.status), raw

    except HTTPError as exc:
        guidance = {
            400: "request or model was rejected",
            401: "API key or gateway token was rejected",
            403: "token lacks access to this model",
            404: "API route or model was not found",
            429: "quota or rate limit was reached",
        }.get(exc.code, "service returned an error")
        raise ProviderError(
            "provider HTTP error: {} ({})".format(exc.code, guidance)
        )

    except URLError as exc:
        reason = str(exc.reason)
        if any(marker in reason.lower() for marker in (
            "ssl", "tls", "connection reset", "eof occurred"
        )):
            raise ProviderError(
                "provider TLS/network connection failed before key or model "
                "validation; check VPN and proxy settings: {}".format(reason)
            ) from exc
        raise ProviderError(
            "provider connection error: {}".format(
                reason
            )
        )

    except OSError as exc:
        raise ProviderError(
            "provider I/O error: {}".format(exc)
        )


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
            transport or _default_transport
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

        payload = {
            "model": self._config.model,
            "messages": [
                {
                    "role": "system",
                    "content": request.system,
                },
                {
                    "role": "user",
                    "content": request.user,
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

        status, raw = self._transport(
            endpoint,
            headers,
            body,
            self._config.timeout_seconds,
            self._config.max_response_bytes,
        )

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
            text = (
                data["choices"][0]
                ["message"]["content"]
            )
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

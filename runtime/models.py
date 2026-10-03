from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional
from urllib.parse import urlparse

_ENV_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    base_url: str
    api_key_env: str
    model: str
    timeout_seconds: int = 120
    max_response_bytes: int = 2_000_000
    allow_insecure_http: bool = False
    proxy_mode: str = "system"
    stream: bool = False
    api_mode: str = "chat_completions"
    temperature_mode: str = "auto"
    max_output_tokens: Optional[int] = None
    extra_body: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_path(cls, path: Path) -> "ProviderConfig":
        data = json.loads(path.read_text(encoding="utf-8"))

        if not isinstance(data, dict):
            raise ValueError("provider config root must be an object")

        allowed = {
            "provider",
            "base_url",
            "api_key_env",
            "model",
            "timeout_seconds",
            "max_response_bytes",
            "allow_insecure_http",
            "proxy_mode",
            "stream", "api_mode", "temperature_mode", "max_output_tokens", "extra_body",
        }

        unknown = sorted(set(data) - allowed)
        if unknown:
            raise ValueError(
                "unknown provider config keys: "
                + ", ".join(unknown)
            )

        try:
            config = cls(**data)
        except TypeError as exc:
            raise ValueError(
                "invalid provider config: {}".format(exc)
            )

        config.validate()
        return config

    def validate(self) -> None:
        if self.provider != "openai-compatible":
            raise ValueError(
                "unsupported provider: {}".format(self.provider)
            )

        if (
            not isinstance(self.base_url, str)
            or not self.base_url.strip()
        ):
            raise ValueError("base_url is required")

        parsed = urlparse(self.base_url)

        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.hostname
        ):
            raise ValueError(
                "base_url must be an absolute http(s) URL"
            )

        if (
            parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "base_url must not contain credentials, "
                "query, or fragment"
            )

        if (
            parsed.scheme == "http"
            and parsed.hostname not in _LOCAL_HOSTS
            and not self.allow_insecure_http
        ):
            raise ValueError(
                "remote plain HTTP requires allow_insecure_http=true"
            )

        if type(self.allow_insecure_http) is not bool:
            raise ValueError("allow_insecure_http must be a boolean")

        if self.proxy_mode not in {"system", "none", "custom"}:
            raise ValueError("proxy_mode must be system, none, or custom")
        if type(self.stream) is not bool:
            raise ValueError("stream must be a boolean")
        if self.api_mode not in {"chat_completions", "responses", "anthropic_messages"}:
            raise ValueError("unsupported api_mode")
        if self.temperature_mode not in {"auto", "omit"}:
            raise ValueError("temperature_mode must be auto or omit")
        if self.max_output_tokens is not None and (
            type(self.max_output_tokens) is not int or not 1 <= self.max_output_tokens <= 128000
        ):
            raise ValueError("max_output_tokens must be an integer from 1 to 128000")
        reserved = {"model", "messages", "input", "instructions", "system", "stream"}
        if not isinstance(self.extra_body, dict) or reserved.intersection(self.extra_body):
            raise ValueError("extra_body must be an object without core request fields")
        def contains_credentials(value):
            if isinstance(value, dict):
                return any(str(key).lower() in {"api_key", "apikey", "authorization", "secret", "access_token", "password"}
                           or contains_credentials(child) for key, child in value.items())
            if isinstance(value, list):
                return any(contains_credentials(child) for child in value)
            return False
        if contains_credentials(self.extra_body):
            raise ValueError("credentials belong in the API key field, not extra_body")
        json.dumps(self.extra_body, allow_nan=False)

        if not _ENV_RE.fullmatch(self.api_key_env or ""):
            raise ValueError(
                "api_key_env must be a valid environment variable name"
            )

        if (
            not isinstance(self.model, str)
            or not self.model.strip()
        ):
            raise ValueError("model is required")

        if (
            type(self.timeout_seconds) is not int
            or not 1 <= self.timeout_seconds <= 600
        ):
            raise ValueError(
                "timeout_seconds must be an integer from 1 to 600"
            )

        if (
            type(self.max_response_bytes) is not int
            or not 1024
            <= self.max_response_bytes
            <= 20_000_000
        ):
            raise ValueError(
                "max_response_bytes must be between "
                "1024 and 20000000"
            )

    def resolve_api_key(
        self,
        environ: Optional[Mapping[str, str]] = None,
    ) -> str:
        env = os.environ if environ is None else environ
        value = env.get(self.api_key_env, "")

        if not value:
            raise ValueError(
                "required API key environment variable "
                "is not set: {}".format(self.api_key_env)
            )

        return value

    def redacted(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "api_key_env": self.api_key_env,
            "model": self.model,
            "timeout_seconds": self.timeout_seconds,
            "max_response_bytes": self.max_response_bytes,
            "allow_insecure_http": self.allow_insecure_http,
            "proxy_mode": self.proxy_mode,
            "stream": self.stream,
            "api_mode": self.api_mode,
            "temperature_mode": self.temperature_mode,
            "max_output_tokens": self.max_output_tokens,
            "extra_body": self.extra_body,
        }

    def identity(self) -> Dict[str, str]:
        """Transport tuning may change during resume; service/model must not."""
        return {"provider": self.provider, "base_url": self.base_url.rstrip("/"),
                "model": self.model, "api_key_env": self.api_key_env,
                "api_mode": self.api_mode}


@dataclass(frozen=True)
class GenerationRequest:
    system: str
    user: str
    temperature: float = 0.1
    images: tuple[str, ...] = ()

    def validate(self) -> None:
        if (
            not isinstance(self.system, str)
            or not self.system.strip()
        ):
            raise ValueError("system prompt is required")

        if (
            not isinstance(self.user, str)
            or not self.user.strip()
        ):
            raise ValueError("user prompt is required")

        if (
            isinstance(self.temperature, bool)
            or not isinstance(self.temperature, (int, float))
            or not 0 <= float(self.temperature) <= 2
        ):
            raise ValueError(
                "temperature must be between 0 and 2"
            )
        if len(self.images) > 3 or any(
            not isinstance(image, str)
            or not image.startswith(("data:image/png;base64,", "data:image/jpeg;base64,", "data:image/webp;base64,"))
            or len(image) > 12_000_000
            for image in self.images
        ):
            raise ValueError("up to three PNG, JPEG or WebP images are supported")


@dataclass(frozen=True)
class GenerationResponse:
    text: str
    model: str
    provider: str
    response_id: Optional[str]
    usage: Dict[str, Any]

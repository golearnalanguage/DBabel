from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
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
        ):
            raise ValueError(
                "plain HTTP is allowed only for localhost providers"
            )

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
        }


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

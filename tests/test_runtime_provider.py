import json
import tempfile
import unittest
from pathlib import Path

from providers.base import ProviderError
from providers.openai_compatible import (
    OpenAICompatibleProvider,
)
from runtime.models import (
    GenerationRequest,
    ProviderConfig,
)


class ProviderConfigTests(unittest.TestCase):
    def test_remote_plain_http_is_rejected(self):
        config = ProviderConfig(
            "openai-compatible",
            "http://example.com/v1",
            "KEY",
            "model-a",
        )

        with self.assertRaises(ValueError):
            config.validate()

    def test_local_plain_http_is_allowed(self):
        config = ProviderConfig(
            "openai-compatible",
            "http://127.0.0.1:8000/v1",
            "KEY",
            "model-a",
        )

        config.validate()

    def test_unknown_config_keys_fail_closed(
        self,
    ):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "provider.json"

            path.write_text(
                json.dumps({
                    "provider":
                        "openai-compatible",
                    "base_url":
                        "https://example.com/v1",
                    "api_key_env":
                        "KEY",
                    "model":
                        "model-a",
                    "unexpected":
                        True,
                }),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                ProviderConfig.from_path(path)

    def test_missing_key_is_rejected(self):
        config = ProviderConfig(
            "openai-compatible",
            "https://example.com/v1",
            "DBABEL_TEST_KEY",
            "model-a",
        )

        with self.assertRaises(ValueError):
            config.resolve_api_key({})


class ProviderTests(unittest.TestCase):
    def config(self):
        return ProviderConfig(
            "openai-compatible",
            "https://example.com/v1",
            "DBABEL_TEST_KEY",
            "model-a",
        )

    def test_request_contract_and_response_parse(
        self,
    ):
        observed = {}

        def transport(
            url,
            headers,
            body,
            timeout,
            max_bytes,
        ):
            observed.update(
                url=url,
                headers=dict(headers),
                body=json.loads(
                    body.decode("utf-8")
                ),
                timeout=timeout,
                max_bytes=max_bytes,
            )

            return 200, json.dumps({
                "id": "resp-1",
                "model": "model-a",
                "choices": [{
                    "message": {
                        "content": "translated"
                    }
                }],
                "usage": {
                    "total_tokens": 12
                },
            }).encode("utf-8")

        provider = OpenAICompatibleProvider(
            self.config(),
            {
                "DBABEL_TEST_KEY":
                    "top-secret"
            },
            transport,
        )

        result = provider.generate(
            GenerationRequest(
                system="system",
                user="user",
            )
        )

        self.assertEqual(
            result.text,
            "translated",
        )

        self.assertEqual(
            observed["url"],
            (
                "https://example.com/v1/"
                "chat/completions"
            ),
        )

        self.assertEqual(
            observed["headers"]
            ["Authorization"],
            "Bearer top-secret",
        )

        self.assertFalse(
            observed["body"]["stream"]
        )

    def test_malformed_response_fails_closed(
        self,
    ):
        provider = OpenAICompatibleProvider(
            self.config(),
            {
                "DBABEL_TEST_KEY":
                    "top-secret"
            },
            lambda *args: (
                200,
                b'{"choices":[]}',
            ),
        )

        with self.assertRaises(
            ProviderError
        ):
            provider.generate(
                GenerationRequest(
                    system="system",
                    user="user",
                )
            )

    def test_response_size_limit_is_enforced(
        self,
    ):
        config = ProviderConfig(
            "openai-compatible",
            "https://example.com/v1",
            "DBABEL_TEST_KEY",
            "model-a",
            max_response_bytes=1024,
        )

        provider = OpenAICompatibleProvider(
            config,
            {
                "DBABEL_TEST_KEY":
                    "top-secret"
            },
            lambda *args: (
                200,
                b"x" * 1025,
            ),
        )

        with self.assertRaises(
            ProviderError
        ):
            provider.generate(
                GenerationRequest(
                    system="system",
                    user="user",
                )
            )


if __name__ == "__main__":
    unittest.main()

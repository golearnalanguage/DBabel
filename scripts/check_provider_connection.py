"""Make one small request through the same provider used by translation.

This may incur provider usage. No API key is written to stdout or stderr.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from providers.openai_compatible import OpenAICompatibleProvider
from runtime.models import GenerationRequest, ProviderConfig


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-config", type=Path, required=True)
    parser.add_argument("--task-check", action="store_true",
                        help="Also verify one small synthetic translation contract (uses provider tokens).")
    args = parser.parse_args()
    try:
        config = ProviderConfig.from_path(args.provider_config)
        provider = OpenAICompatibleProvider(config)
        if args.task_check:
            from providers.preflight import task_preflight
            report = task_preflight(provider)
            print(json.dumps(report, ensure_ascii=False))
            return 0 if report["contract_verified"] else 1
        response = provider.generate(
            GenerationRequest(
                system="Reply with exactly OK.",
                user="OK",
            )
        )
    except Exception as exc:
        print("Connection test failed: {}".format(exc), file=sys.stderr)
        return 1
    print(json.dumps({
        "status": "CONNECTED",
        "model": response.model,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

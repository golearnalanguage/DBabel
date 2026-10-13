"""A small real task contract probe, separate from connection availability."""
from __future__ import annotations
from collections import Counter
import json

from runtime.models import GenerationRequest
from runtime.translation import protected_literals


def task_preflight(provider):
    source = "请检查 /data/db/dm.ini，并确认 ${DB_HOME} 与 --exec_mode 保持不变。"
    payload = {"task": "DBabel task capability probe", "source_language": "zh-CN",
               "target_language": "en", "units": [{"id": "PROBE_1", "source": source}],
               "response_contract": {"units": [{"id": "PROBE_1", "suggested_target": "complete English translation"}]}}
    response = provider.generate(GenerationRequest(
        system="Translate the supplied Chinese instruction into English. Preserve all paths, placeholders and command flags exactly. Return only the requested JSON object.",
        user=json.dumps(payload, ensure_ascii=False)))
    findings = []
    try:
        decoded = json.loads(response.text)
        rows = decoded["units"]
        if not isinstance(rows, list) or len(rows) != 1 or rows[0].get("id") != "PROBE_1":
            raise ValueError("unit identity or count differs")
        target = rows[0].get("suggested_target")
        if not isinstance(target, str) or not target.strip():
            raise ValueError("missing suggested_target")
        literals = set(protected_literals(source)) | set(protected_literals(target))
        if any(source.count(literal) != target.count(literal) for literal in literals):
            findings.append("protected literals changed")
        if any("\u4e00" <= char <= "\u9fff" for char in target):
            findings.append("ordinary Chinese remains in the English probe")
    except (ValueError, KeyError, TypeError, AttributeError):
        findings.append("response does not satisfy the translation JSON contract")
    return {"status": "TASK_READY" if not findings else "CONTRACT_FAILED",
            "connected": True, "contract_verified": not findings,
            "model": response.model, "findings": findings,
            "usage": response.usage, "diagnostics": response.diagnostics,
            "coverage": "one bounded synthetic translation; document-wide performance is unmeasured"}

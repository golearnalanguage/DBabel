"""Normalize complete JSON/SSE answers without accepting partial model output.

The decoder implements the public wire formats, independently of SDK internals.
Reasoning deltas and tool calls are never substituted for final answer text.
"""
from __future__ import annotations

import json
from typing import Any, Dict

from providers.base import ProviderError, ProviderTransientError, ProviderResponseInterrupted


def text_content(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content
                       if isinstance(part, dict) and part.get("type") in {"text", "output_text"}
                       and isinstance(part.get("text"), str))
    return None


def service_error(value: Dict[str, Any]) -> None:
    issue = value.get("error")
    if not issue:
        return
    issue = issue if isinstance(issue, dict) else {"message": str(issue)}
    status = issue.get("status") or issue.get("code")
    status = int(status) if str(status).isdigit() else None
    message = str(issue.get("message") or issue.get("type") or "service returned an error")[:350]
    error = ProviderTransientError if status in {408, 409, 425, 429} or (status and status >= 500) else ProviderError
    raise error("provider stream/service error: " + message, status=status)


def normalize_json(data: Dict[str, Any], mode: str) -> Dict[str, Any]:
    service_error(data)
    if mode == "chat_completions":
        return data
    if mode == "responses":
        if data.get("status") in {"incomplete", "failed", "cancelled"}:
            raise ProviderResponseInterrupted("provider response did not complete: " + str(data.get("status")))
        content = "".join(text_content(item.get("content")) or ""
                          for item in data.get("output", []) if isinstance(item, dict) and item.get("type") == "message")
        # output_text is exposed by a few compatible gateways as a convenience.
        content = content or data.get("output_text", "")
        finish = "stop"
    else:
        content = text_content(data.get("content"))
        finish = "length" if data.get("stop_reason") == "max_tokens" else data.get("stop_reason")
    return {"id": data.get("id"), "model": data.get("model"), "usage": data.get("usage", {}),
            "choices": [{"message": {"content": content}, "finish_reason": finish}]}


def decode_response(raw: bytes, mode: str) -> Dict[str, Any]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ProviderResponseInterrupted("provider response contains incomplete UTF-8") from exc
    if text.lstrip().startswith(("{", "[")):
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise ProviderResponseInterrupted("provider JSON response was truncated or malformed") from exc
        if not isinstance(data, dict):
            raise ProviderError("provider response root must be an object")
        return normalize_json(data, mode)

    # SSE events are separated by blank lines; comments are heartbeat frames.
    events = []
    lines = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if not line:
            if lines:
                events.append("\n".join(lines))
                lines = []
        elif line.startswith("data:"):
            value = line[5:]
            lines.append(value[1:] if value.startswith(" ") else value)
    if lines:
        events.append("\n".join(lines))
    chunks = []
    complete = False
    finish = None
    result = {"usage": {}}
    for event in events:
        if event.strip() == "[DONE]":
            complete = True
            continue
        try:
            data = json.loads(event)
        except ValueError as exc:
            raise ProviderResponseInterrupted("provider SSE event was truncated or malformed") from exc
        if not isinstance(data, dict):
            raise ProviderError("provider SSE event must be an object")
        service_error(data)
        result.update({k: data[k] for k in ("id", "model") if data.get(k) is not None})
        if isinstance(data.get("usage"), dict):
            result["usage"].update(data["usage"])
        if mode == "chat_completions":
            for choice in data.get("choices", []):
                if choice.get("index", 0) != 0:
                    continue
                delta = choice.get("delta") or choice.get("message") or {}
                content = text_content(delta.get("content"))
                if content:
                    chunks.append(content)
                if choice.get("finish_reason"):
                    finish = choice["finish_reason"]
                    complete = True
        elif mode == "responses":
            kind = data.get("type")
            if kind == "response.output_text.delta":
                chunks.append(data.get("delta", ""))
            if kind in {"response.failed", "response.incomplete", "error"}:
                raise ProviderResponseInterrupted("provider Responses stream did not complete")
            if kind == "response.completed":
                return normalize_json(data["response"], mode)
        else:
            if data.get("type") == "message_start":
                result.update({k: v for k, v in data.get("message", {}).items()
                               if k in {"id", "model", "usage"}})
            if data.get("type") == "content_block_delta" and data.get("delta", {}).get("type") == "text_delta":
                chunks.append(data["delta"].get("text", ""))
            if data.get("type") == "message_delta":
                finish = "length" if data.get("delta", {}).get("stop_reason") == "max_tokens" else data.get("delta", {}).get("stop_reason")
                result["usage"].update(data.get("usage", {}))
            if data.get("type") == "message_stop":
                complete = True
    if not complete:
        raise ProviderResponseInterrupted("provider stream disconnected before a completion marker")
    result["choices"] = [{"message": {"content": "".join(chunks)}, "finish_reason": finish}]
    return result

"""Bounded, credential-safe provider failures shared by probes and project runs."""
from __future__ import annotations

import errno
import json
import re
import socket
import ssl

from providers.base import ProviderError, ProviderResponseInterrupted, ProviderTransientError


# Titles describe the observed failure. HTTP errors cannot identify which hop
# produced them, so service/proxy attribution remains explicit in the wording.
_MESSAGES = {
    "AUTHENTICATION_FAILED": ("API 令牌被拒绝", "API token rejected",
        "服务返回认证失败，当前令牌未被接受。", "The service rejected the supplied API or gateway token.",
        ["在服务控制台检查令牌是否有效、过期或已撤销。", "确认填写的是当前网关签发的令牌，再保存并测试。"],
        ["Check whether the token is valid, expired or revoked in the service console.", "Save a token issued by this gateway and test again."]),
    "ACCESS_DENIED": ("令牌没有访问权限", "Access denied",
        "服务拒绝此令牌访问请求的模型或接口。", "The service denied this token access to the requested model or API route.",
        ["检查令牌的模型、分组、接口权限及 IP 限制。", "向服务管理员确认此模型对当前令牌开放。"],
        ["Check model, group, route and IP restrictions on the token.", "Ask the service administrator to confirm access to this model."]),
    "QUOTA_EXHAUSTED": ("余额或配额不足", "Balance or quota exhausted",
        "服务报告当前账户余额或使用配额不足。", "The service reported insufficient account balance or usage quota.",
        ["检查余额、配额和令牌用量限制。", "补充额度后继续已有运行，已保存批次可复用。"],
        ["Check balance, quota and token usage limits.", "Resume the saved run after quota is restored."]),
    "REQUEST_REJECTED": ("接口拒绝请求参数", "Request parameters rejected",
        "服务认为请求参数、模型配置或请求内容无效。", "The service rejected request parameters, model configuration or content.",
        ["查看服务错误详情，核对模型 ID 与接口协议。", "按服务文档检查模型附加参数；仅在明确拒绝时调整流式或温度设置。"],
        ["Check the service error, model ID and API protocol.", "Check additional parameters against service documentation; adjust stream or temperature only when explicitly rejected."]),
    "ROUTE_OR_MODEL_NOT_FOUND": ("接口路径或模型未找到", "API route or model not found",
        "服务未找到请求的接口路径或模型。", "The service could not find the requested API route or model.",
        ["核对 Base URL、接口协议和准确模型 ID。", "确认模型已在该网关启用。"],
        ["Check the base URL, API protocol and exact model ID.", "Confirm this model is enabled on the gateway."]),
    "RATE_LIMITED": ("请求受到限流", "Rate limit reached",
        "服务限制了请求频率或当前用量；本次已按重试策略等待。", "The service limited request rate or usage; this request followed the bounded retry policy.",
        ["稍后继续已有运行，避免同时启动多份翻译。", "检查请求频率、并发和令牌配额限制。"],
        ["Resume later and avoid simultaneous translation runs.", "Check request-rate, concurrency and token quota limits."]),
    "SERVICE_UNAVAILABLE": ("服务或中间代理暂时不可用", "Service or intermediary proxy unavailable",
        "请求收到了服务或中间代理的失败响应，尚未返回可用的模型答案。", "The service or an intermediary proxy returned a failure before a usable model answer was available.",
        ["检查公司网络、VPN 及系统代理例外规则。", "查看网关状态，携带请求 ID 和服务错误详情联系管理员；恢复后继续已有运行。"],
        ["Check company network, VPN and system proxy bypass rules.", "Check gateway status and give the administrator the request ID and service error; resume after recovery."]),
    "TIMEOUT": ("API 响应超时", "API response timed out",
        "连接或读取等待超过超时限制，或者服务返回了超时响应。", "Connection or response reading exceeded its timeout, or the service returned a timeout response.",
        ["检查网络和网关延迟，确认读取超时设置适合该模型。", "恢复后继续已有运行，已保存批次会保留；长回答可减少批次或输出量。"],
        ["Check network and gateway latency and the model's read timeout.", "Resume saved progress after recovery; reduce batch or output size for long answers."]),
    "DNS_FAILED": ("服务域名解析失败", "Service hostname resolution failed",
        "系统无法把服务域名解析为网络地址，尚未取得模型响应。", "The system could not resolve the service hostname to a network address.",
        ["核对服务地址拼写。", "连接公司网络或 VPN，检查 DNS 设置后重新测试。"],
        ["Check the service hostname spelling.", "Connect to company network or VPN and check DNS settings before testing again."]),
    "TLS_FAILED": ("HTTPS 安全连接失败", "HTTPS connection failed",
        "TLS 握手或证书验证失败，尚未取得模型响应。", "TLS negotiation or certificate verification failed before a model response was received.",
        ["核对 HTTPS 地址和服务证书有效期。", "检查企业根证书、VPN 和代理的证书设置；保持证书验证开启。"],
        ["Check the HTTPS address and certificate validity.", "Check corporate CA, VPN and proxy certificate configuration; keep certificate verification enabled."]),
    "CONNECTION_RESET": ("网络连接被重置", "Network connection reset",
        "服务或网络中间节点在响应完成前重置了连接。", "The service or a network intermediary reset the connection before the response completed.",
        ["检查网络、VPN、代理及网关访问规则。", "重新测试，持续出现时携带错误详情联系服务管理员；已有进度可继续。"],
        ["Check network, VPN, proxy and gateway access rules.", "Test again and contact the service administrator if it persists; saved progress can be resumed."]),
    "CONNECTION_FAILED": ("API 网络连接失败", "API network connection failed",
        "客户端未能建立或维持到服务的网络连接。", "The client could not establish or maintain a network connection to the service.",
        ["检查服务地址、端口、公司网络和 VPN。", "核对网络连接方式与代理设置，再测试。"],
        ["Check service address, port, company network and VPN.", "Check the selected network route and proxy settings, then test again."]),
    "RESPONSE_INTERRUPTED": ("模型响应未完整结束", "Model response incomplete",
        "响应被截断、没有最终答案或达到输出限制，本批次尚未完成。", "The response was interrupted, lacked a final answer or reached an output limit; this batch remains incomplete.",
        ["查看详情，检查读取超时、流式支持和输出 token 限制。", "继续已有运行；程序会保留已保存批次，必要时缩小未完成批次。"],
        ["Check read timeout, streaming support and output token limits using the details.", "Resume the saved run; completed batches are preserved and unfinished work may be split."]),
    "CONTRACT_FAILED": ("模型输出未满足翻译要求", "Translation output contract failed",
        "模型返回内容缺少要求的格式、单元或译文，或改变了受保护字面量。", "The model output lacked required format, units or translation, or changed protected technical literals.",
        ["查看具体格式或字面量检查结果。", "选择支持结构化翻译的模型，核对接口协议和模型附加参数后重新测试。"],
        ["Inspect the format or protected-literal findings.", "Choose a model capable of structured translation and check API protocol and additional parameters before testing again."]),
    "INVALID_RESPONSE": ("接口返回了无效响应", "Invalid API response",
        "响应格式与所选接口协议不一致，无法解析为完整的模型答案。", "The response format did not match the selected API protocol and could not be parsed into a complete answer.",
        ["核对 Chat Completions、Responses 或 Messages 协议。", "检查网关是否返回登录页面或其他非模型内容，再重新测试。"],
        ["Check the Chat Completions, Responses or Messages protocol.", "Check whether the gateway returned a login page or other non-model content, then test again."]),
    "CONFIGURATION_ERROR": ("API 配置未通过检查", "API configuration invalid",
        "配置、密钥环境变量或请求客户端未满足本地检查要求。", "Configuration, key environment variable or request client failed local validation.",
        ["根据错误详情修正服务地址、模型、密钥或请求客户端配置。", "保存配置后重新测试。"],
        ["Correct service URL, model, key or request-client configuration using the details.", "Save the configuration and test again."]),
    "PROVIDER_ERROR": ("API 请求未完成", "API request failed",
        "接口调用或模型响应发生错误，详情中保留了可用的原因。", "The API request or model response failed; available details describe the cause.",
        ["查看服务错误详情、请求 ID 和尝试次数。", "检查配置及服务状态；修复后继续已有运行。"],
        ["Inspect the service message, request ID and attempt count.", "Check configuration and service status; resume the saved run after fixing the issue."]),
}
_MESSAGES["SERVICE_FAILED"] = ("服务或中间代理处理请求失败", "Service or intermediary proxy failed",
    "服务或中间代理返回服务器错误，本次未获得可用的模型答案。", "The service or an intermediary proxy returned a server error before a usable model answer was available.",
    ["检查网关和服务状态，稍后继续已有运行。", "持续出现时携带请求 ID、错误详情和 HTTP 状态联系服务管理员。"],
    ["Check gateway and service status, then resume the saved run later.", "If it persists, give the service administrator the request ID, error details and HTTP status."])


def exception_chain(exc):
    pending, result, seen = [exc], [], set()
    while pending and len(result) < 32:
        current = pending.pop(0)
        if not isinstance(current, BaseException) or id(current) in seen:
            continue
        seen.add(id(current))
        result.append(current)
        pending.extend((current.__cause__, current.__context__, getattr(current, "reason", None)))
    return result


def safe_text(value, secrets=(), limit=768):
    if value is None: return None
    text = str(value)
    for secret in sorted(set(s for s in secrets if isinstance(s, str) and s), key=len, reverse=True):
        text = text.replace(secret, "[redacted]")
        # A bounded transport read can end partway through an echoed token.
        for size in range(len(secret) - 1, min(4, len(secret)) - 1, -1):
            if text.endswith(secret[:size]):
                text = text[:-size] + "[redacted]"
                break
    text = re.sub(r"(?i)\bbearer\s+[^\s\"'<>;,]+", "Bearer [redacted]", text)
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{12,}", "[redacted]", text)
    text = re.sub(r"(?i)([a-z][a-z0-9+.-]*://)[^/\s@]+@", r"\1[redacted]@", text)
    text = re.sub(r"(?i)([?&](?:api[_-]?key|access_token|token|password|secret)=)[^&#\s]+", r"\1[redacted]", text)
    text = re.sub(r"(?i)([\"']?(?:api[_-]?key|access_token|authorization|password|secret)[\"']?\s*[:=]\s*)[\"']?[^\s,;\"']+", r"\1[redacted]", text)
    return text[:limit]


def known_secrets(exc, extra=()):
    return tuple(extra) + tuple(value for item in exception_chain(exc) for value in getattr(item, "_secrets", ()))


def service_message(value):
    if isinstance(value, bytes): value = value[:4096].decode("utf-8", errors="replace")
    if isinstance(value, str):
        try: value = json.loads(value)
        except ValueError:
            return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", value)).strip() or None
    if isinstance(value, dict):
        issue = value.get("error", value)
        if isinstance(issue, dict):
            for key in ("message", "code", "type"):
                detail = issue.get(key)
                if isinstance(detail, str) or type(detail) is int:
                    if str(detail): return str(detail)
            return None
        if isinstance(issue, str): return issue
    return None


def service_request_id(value, headers=None):
    """Prefer a response header, then an explicit ID or ID-labelled message."""
    header = (headers.get("x-request-id") or headers.get("request-id")) if headers is not None else None
    if isinstance(header, str) and re.fullmatch(r"[A-Za-z0-9._-]{1,256}", header):
        return header
    if isinstance(value, bytes): value = value[:4096].decode("utf-8", errors="replace")
    if isinstance(value, str):
        try: value = json.loads(value)
        except ValueError: pass
    candidates = [value]
    if isinstance(value, dict): candidates.append(value.get("error"))
    for candidate in candidates:
        if isinstance(candidate, dict):
            for key in ("request_id", "requestId", "request-id"):
                request_id = candidate.get(key)
                if isinstance(request_id, str) and re.fullmatch(r"[A-Za-z0-9._-]{1,256}", request_id):
                    return request_id
    message = service_message(value)
    if message:
        match = re.search(r"(?i)\brequest[ _-]*id\s*[:=]\s*([A-Za-z0-9][A-Za-z0-9._-]{0,255})(?=$|[\s)\],;}])", message)
        if match: return match.group(1)
    return None


def is_provider_failure(exc):
    return any(isinstance(item, ProviderError) or type(item).__name__ in {
        "RuntimeTranslationError", "SemanticAdjudicationError"} for item in exception_chain(exc))


def provider_error_report(exc, *, secrets=(), fallback_kind=None):
    chain = exception_chain(exc)
    credentials = list(secrets)
    details = {}
    for item in reversed(chain):
        credentials.extend(getattr(item, "_secrets", ()))
        details.update(getattr(item, "details", {}))
    provider = next((item for item in chain if isinstance(item, ProviderError)), None)
    status = next((getattr(item, "status", None) for item in chain if getattr(item, "status", None) is not None), None)
    if type(status) is not int: status = None
    kind = next((getattr(item, "kind", None) for item in chain if getattr(item, "kind", None)), None)
    if kind not in _MESSAGES: kind = None
    if kind is None and status is not None:
        kind = {400: "REQUEST_REJECTED", 401: "AUTHENTICATION_FAILED", 402: "QUOTA_EXHAUSTED",
            403: "ACCESS_DENIED", 404: "ROUTE_OR_MODEL_NOT_FOUND", 408: "TIMEOUT", 422: "REQUEST_REJECTED",
            429: "RATE_LIMITED", 502: "SERVICE_UNAVAILABLE", 503: "SERVICE_UNAVAILABLE", 504: "TIMEOUT"}.get(status,
                "SERVICE_FAILED" if 500 <= status <= 599 else "PROVIDER_ERROR")
    if kind is None:
        if any(isinstance(item, socket.gaierror) for item in chain): kind = "DNS_FAILED"
        elif any(isinstance(item, ssl.SSLError) for item in chain): kind = "TLS_FAILED"
        elif any(isinstance(item, ConnectionResetError) or getattr(item, "errno", None) == errno.ECONNRESET for item in chain): kind = "CONNECTION_RESET"
        elif any(isinstance(item, (TimeoutError, socket.timeout)) or type(item).__name__ in {"APITimeoutError", "ConnectTimeout", "ReadTimeout", "WriteTimeout", "PoolTimeout"} for item in chain): kind = "TIMEOUT"
        elif isinstance(provider, ProviderResponseInterrupted): kind = "RESPONSE_INTERRUPTED"
        elif any(isinstance(item, ConnectionError) or type(item).__name__ in {"URLError", "APIConnectionError", "ConnectError", "ReadError"} for item in chain): kind = "CONNECTION_FAILED"
        elif any(type(item).__name__ in {"RuntimeTranslationError", "SemanticAdjudicationError"} for item in chain): kind = "CONTRACT_FAILED"
        elif isinstance(provider, ProviderTransientError): kind = "CONNECTION_FAILED"
        elif isinstance(provider, ProviderError) and any(marker in str(provider).lower() for marker in ("invalid protocol", "missing choices", "response root", "response exceeded", "compressed content")): kind = "INVALID_RESPONSE"
        elif any(isinstance(item, ValueError) for item in chain): kind = "CONFIGURATION_ERROR"
        else: kind = fallback_kind if fallback_kind in _MESSAGES else "PROVIDER_ERROR"
    title_zh, title_en, explanation_zh, explanation_en, actions_zh, actions_en = _MESSAGES[kind]
    attempts = details.get("attempts", 1 if provider else 0)
    attempts = attempts if type(attempts) is int and 0 <= attempts <= 1000 else 0
    original = next((str(item) for item in reversed(chain) if str(item)), str(exc))
    message = details.get("service_message")
    if not isinstance(message, str) or not message: message = original
    report = {"type": kind, "title_zh": title_zh, "title_en": title_en,
        "explanation_zh": explanation_zh, "explanation_en": explanation_en,
        "actions_zh": list(actions_zh), "actions_en": list(actions_en),
        "http_status": status if type(status) is int and 100 <= status <= 599 else None,
        "service_message": message, "request_id": details.get("request_id") if isinstance(details.get("request_id"), str) else None,
        "attempts": attempts,
        "backend": details.get("backend") if isinstance(details.get("backend"), str) else None,
        "route": details.get("route") if isinstance(details.get("route"), str) else None}
    # All textual report fields, including identifiers, pass through one filter.
    for key, value in report.items():
        if isinstance(value, str): report[key] = safe_text(value, credentials, 128 if key == "request_id" else 768)
        elif isinstance(value, list): report[key] = [safe_text(item, credentials) for item in value]
    return report

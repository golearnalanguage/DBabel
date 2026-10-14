"""Exercise desktop task-report handling and provider persistence without launching UI."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform == 'darwin' and shutil.which('swiftc'),
                     'macOS Swift compiler required')
class DesktopProviderChecks(unittest.TestCase):
    def run_swift(self, source):
        with tempfile.TemporaryDirectory(prefix='dbabel-desktop-check-') as directory:
            temporary = Path(directory)
            main = temporary / 'main.swift'
            main.write_text(source, encoding='utf-8')
            binary = temporary / 'check'
            subprocess.run(['swiftc', str(ROOT / 'desktop/macos/DesktopBackend.swift'),
                            str(main), '-o', str(binary)], check=True, capture_output=True,
                           text=True, timeout=120)
            result = subprocess.run([str(binary)], check=True, capture_output=True,
                                    text=True, timeout=15)
            self.assertIn('Desktop provider checks passed.', result.stdout)

    def test_task_results_and_saved_transport_round_trip(self):
        source = r'''
import Foundation

let ready = DesktopController.providerCheckResult(exitStatus: 0,
    output: #"{"status":"TASK_READY","contract_verified":true}"#, error: "")
assert(ready.success)
let failed = DesktopController.providerCheckResult(exitStatus: 1,
    output: #"{"status":"CONTRACT_FAILED","connected":true,"contract_verified":false,"findings":["protected literals changed"]}"#,
    error: "")
assert(!failed.success && failed.detail.contains("protected literals changed"))
assert(failed.detail.contains("API connected"))
let invalid = DesktopController.providerCheckResult(exitStatus: 0, output: "OK", error: "")
assert(!invalid.success && !invalid.detail.isEmpty)
let inconsistent = DesktopController.providerCheckResult(exitStatus: 0,
    output: #"{"status":"TASK_READY","contract_verified":false}"#, error: "")
assert(!inconsistent.success)
let network = DesktopController.providerCheckResult(exitStatus: 1,
    output: "", error: "provider HTTP error: 401")
assert(!network.success && network.detail.contains("401"))

let old: [String: Any] = ["baseURL":"https://api.example.com/v1", "model":"synthetic",
    "apiKeyEnv":"DBABEL_API_KEY", "proxyURL":"", "timeoutSeconds":120,
    "maxResponseBytes":2000000]
let legacy = try JSONDecoder().decode(ProviderSettings.self,
    from: JSONSerialization.data(withJSONObject: old))
assert(legacy.effectiveTransportBackend == "auto" && legacy.validationError() == nil)
for client in ["auto", "stdlib", "sdk"] {
    var value = old
    value["transportBackend"] = client
    let settings = try JSONDecoder().decode(ProviderSettings.self,
        from: JSONSerialization.data(withJSONObject: value))
    let saved = try JSONDecoder().decode(ProviderSettings.self,
        from: JSONEncoder().encode(settings))
    assert(saved.effectiveTransportBackend == client && saved.validationError() == nil)
    let path = try saved.temporaryFile()
    defer { try? FileManager.default.removeItem(at: path) }
    let exported = try JSONSerialization.jsonObject(with: Data(contentsOf: path)) as! [String: Any]
    assert(exported["transport_backend"] as? String == client)
}
var bad = old
bad["transportBackend"] = "unknown"
let unsupported = try JSONDecoder().decode(ProviderSettings.self,
    from: JSONSerialization.data(withJSONObject: bad))
assert(unsupported.validationError() != nil)
print("Desktop provider checks passed.")
'''
        self.run_swift(source)

    def test_structured_errors_are_localized_complete_and_safe_in_both_flows(self):
        source = r'''
import Foundation
import AppKit

let secret = "sk-synthetic-secretvalue"
func output(_ report: [String: Any], status: String = "FAILED") throws -> String {
    let data = try JSONSerialization.data(withJSONObject: ["status": status, "error": report])
    return String(data: data, encoding: .utf8)!
}
var authentication: [String: Any] = [
    "type": "AUTHENTICATION_FAILED", "title_zh": "身份验证失败", "title_en": "Authentication failed",
    "explanation_zh": "服务拒绝了当前密钥。", "explanation_en": "The service rejected the current key.",
    "actions_zh": ["重新核对密钥。", "保存正确的密钥后重新测试。"],
    "actions_en": ["Check the API key.", "Save the correct key, then test again."],
    "http_status": 401, "service_message": "Invalid credentials\nAuthorization: Bearer " + secret,
    "request_id": "req-auth-1", "attempts": 1, "backend": "sdk",
    "route": "http://proxy-user:proxy-password@127.0.0.1:1082", "private_metadata": secret
]
for language in ["zh-CN", "en"] {
    let checked = DesktopController.providerCheckResult(exitStatus: 1,
        output: try output(authentication), error: "old generic stderr", language: language, secrets: [secret])
    let translated = DesktopController.translationFailureMessage(
        manifest: ["failure": ["stage": "TRANSLATION", "reason": "old generic reason", "provider_error": authentication]],
        error: "old generic stderr", language: language, secrets: [secret])
    assert(!checked.success && translated == checked.detail)
    assert(checked.detail.contains("AUTHENTICATION_FAILED") && checked.detail.contains("HTTP 401"))
    assert(checked.detail.contains("req-auth-1") && checked.detail.contains("sdk"))
    assert(checked.detail.contains("127.0.0.1:1082") && checked.detail.contains("Invalid credentials\n"))
    assert(!checked.detail.contains(secret) && !checked.detail.contains("proxy-password"))
    assert(!checked.detail.contains("old generic"))
    if language == "zh-CN" {
        assert(checked.detail.contains("错误类型：身份验证失败") && checked.detail.contains("原因\n"))
        assert(checked.detail.contains("操作步骤\n1. 重新核对密钥。\n2."))
        assert(checked.detail.contains("服务原文\n") && checked.detail.contains("尝试次数: 1"))
        assert(checked.detail.contains("网络路由:") && !checked.detail.contains("Error type:"))
    } else {
        assert(checked.detail.contains("Error type: Authentication failed") && checked.detail.contains("Reason\n"))
        assert(checked.detail.contains("Next steps\n1. Check the API key.\n2."))
        assert(checked.detail.contains("Service response\n") && checked.detail.contains("Attempts: 1"))
        assert(checked.detail.contains("Network route:") && !checked.detail.contains("错误类型"))
    }
}
var unavailable = authentication
unavailable["type"] = "SERVICE_UNAVAILABLE"
unavailable["title_zh"] = "服务暂时不可用"
unavailable["title_en"] = "Service unavailable"
unavailable["explanation_zh"] = "服务或中间代理暂时不可用。"
unavailable["explanation_en"] = "The service or an intermediate proxy is temporarily unavailable."
unavailable["actions_zh"] = ["稍后重试。", "联系服务维护人员并提供请求 ID。"]
unavailable["actions_en"] = ["Retry later.", "Give the request ID to the service operator."]
unavailable["http_status"] = 503
unavailable["attempts"] = 3
unavailable["service_message"] = "Temporarily unavailable\n" + String(repeating: "context ", count: 120) + "upstream status confirmed"
let service = DesktopController.providerCheckResult(exitStatus: 1, output: try output(unavailable), error: "")
assert(service.detail.contains("HTTP 503") && service.detail.contains("Attempts: 3"))
assert(service.detail.contains("Retry later.") && service.detail.contains("upstream status confirmed"))
assert(service.detail.count > 600 && service.detail.contains("intermediate proxy"))

var network = authentication
network["type"] = "CONNECTION_RESET"
network["title_zh"] = "连接中断"
network["title_en"] = "Connection reset"
network["explanation_zh"] = "连接在返回完整响应前中断。"
network["explanation_en"] = "The connection closed before a complete response arrived."
network["actions_zh"] = ["核对网络与代理，再继续已保存的任务。"]
network["actions_en"] = ["Check the network and proxy, then resume the saved run."]
network["http_status"] = NSNull()
network["request_id"] = NSNull()
network["service_message"] = "Connection reset by peer"
network["route"] = "none"
let disconnected = DesktopController.providerCheckResult(exitStatus: 1, output: try output(network), error: "")
assert(disconnected.detail.contains("CONNECTION_RESET") && disconnected.detail.contains("Connection reset by peer"))
assert(disconnected.detail.contains("resume the saved run") && disconnected.detail.contains("Network route: none"))
assert(!disconnected.detail.contains("HTTP ") && !disconnected.detail.contains("Request ID:"))

var contract = network
contract["type"] = "CONTRACT_FAILED"
contract["title_en"] = "Translation contract failed"
let contractResult = DesktopController.providerCheckResult(exitStatus: 1,
    output: try output(contract, status: "CONTRACT_FAILED"), error: "", language: "en")
assert(contractResult.detail.contains("CONTRACT_FAILED") && contractResult.detail.contains("Next steps\n"))
let legacyReason = "Parser reported:\n" + String(repeating: "located warning\n", count: 80) + "Useful final guidance"
let legacy = DesktopController.translationFailureMessage(
    manifest: ["failure": ["stage": "FORMAT_PROBE", "reason": legacyReason]], error: "", language: "zh-CN")
assert(legacy.contains("文档预检未通过") && legacy.contains("Useful final guidance"))
assert(legacy.contains("Parser reported:\n") && legacy.count > 600)
let oldStderr = DesktopController.providerCheckResult(exitStatus: 1, output: "",
    error: "provider HTTP error: 401\nkey=" + secret, language: "zh-CN", secrets: [secret])
assert(oldStderr.detail.contains("401\n") && !oldStderr.detail.contains(secret))
let numeric = DesktopController.providerCheckResult(exitStatus: 1, output: "", error: "503", language: "zh-CN")
assert(numeric.detail.contains("错误详情\n503") && numeric.detail.contains("操作步骤\n"))
let controller = DesktopController()
var received = [String]()
controller.onTranslationFailure = { message in
    received.append(controller.lastTranslationFailureDetail(language: "en") ?? message)
}
controller.reportTranslationFailure(manifest: ["failure": ["provider_error": unavailable]],
    error: "", language: "en", apiKey: secret)
assert(controller.lastTranslationFailureDetail(language: "en")?.contains("SERVICE_UNAVAILABLE") == true)
controller.openSession(FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".dbreview"))
assert(controller.lastTranslationFailureDetail(language: "en") == nil)
assert(received.count == 2 && received.last!.contains("Choose an existing .dbreview session"))
assert(!received.last!.contains("SERVICE_UNAVAILABLE"))
controller.close()
let sanitized = DesktopController.safeErrorText(String(repeating: "x", count: 20) + secret, limit: 25, secrets: [secret])
assert(!sanitized.contains("sk-syn") && sanitized.contains("…"))
var oversized = unavailable
oversized["service_message"] = String(repeating: "x", count: 100_000) + secret
assert(DesktopController.providerErrorMessage(oversized, secrets: [secret]).count < 18_100)
let detailsView = DiagnosticTextView(frame: NSRect(x: 0, y: 0, width: 550, height: 150))
let detailsScroll = detailsView.scrollView(width: 550, height: 150)
detailsView.stringValue = String(repeating: service.detail + "\n\n", count: 6)
detailsView.layoutManager?.ensureLayout(for: detailsView.textContainer!)
assert(detailsScroll.documentView === detailsView && detailsScroll.hasVerticalScroller)
assert(!detailsView.isEditable && detailsView.isSelectable && !detailsView.isHorizontallyResizable)
assert(detailsView.textContainer?.widthTracksTextView == true && detailsView.frame.height > 150)
assert(detailsView.stringValue.contains("upstream status confirmed"))
print("Desktop provider checks passed.")
'''
        self.run_swift(source)

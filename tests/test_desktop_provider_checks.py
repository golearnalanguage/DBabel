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

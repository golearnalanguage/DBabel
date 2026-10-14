import AppKit
import Foundation
import WebKit
import UniformTypeIdentifiers
import Darwin

final class DiagnosticTextView: NSTextView {
    var stringValue: String {
        get { string }
        set {
            string = newValue
            scrollRangeToVisible(NSRange(location: 0, length: 0))
        }
    }

    func scrollView(width: CGFloat, height: CGFloat) -> NSScrollView {
        isEditable = false
        isSelectable = true
        isRichText = false
        drawsBackground = false
        font = .systemFont(ofSize: 13)
        textColor = .labelColor
        textContainerInset = NSSize(width: 10, height: 10)
        minSize = .zero
        maxSize = NSSize(width: CGFloat.greatestFiniteMagnitude, height: CGFloat.greatestFiniteMagnitude)
        isVerticallyResizable = true
        isHorizontallyResizable = false
        autoresizingMask = .width
        textContainer?.widthTracksTextView = true
        setAccessibilityLabel("DBabel error details")
        let scroll = NSScrollView(frame: NSRect(x: 0, y: 0, width: width, height: height))
        scroll.drawsBackground = false
        scroll.borderType = .bezelBorder
        scroll.hasVerticalScroller = true
        scroll.autohidesScrollers = true
        scroll.documentView = self
        scroll.translatesAutoresizingMaskIntoConstraints = false
        return scroll
    }
}

func chooseFile(extensions: [String], directory: Bool = false) -> URL? {
    let panel = NSOpenPanel()
    panel.canChooseDirectories = directory
    panel.canChooseFiles = !directory
    panel.allowsMultipleSelection = false
    if !directory {
        panel.allowedContentTypes = extensions.compactMap {
            UTType(filenameExtension: $0)
        }
    }
    return panel.runModal() == .OK ? panel.url : nil
}

struct ProviderSettings: Codable {
    let baseURL: String
    let model: String
    let apiKeyEnv: String
    let proxyURL: String
    let timeoutSeconds: Int
    let maxResponseBytes: Int
    let allowInsecureHTTP: Bool?
    let proxyMode: String?
    let apiMode: String?
    let transportBackend: String?
    let stream: Bool?
    let temperatureMode: String?
    let maxOutputTokens: Int?
    let requestOptionsJSON: String?

    var effectiveAPIMode: String { apiMode ?? "chat_completions" }
    var effectiveTransportBackend: String { transportBackend ?? "auto" }

    var effectiveProxyMode: String { proxyMode ?? (proxyURL.isEmpty ? "system" : "custom") }

    var isLocal: Bool {
        guard let host = URLComponents(string: baseURL)?.host?.lowercased() else { return false }
        return ["localhost", "127.0.0.1", "::1"].contains(host)
    }

    func validationError() -> String? {
        guard let url = URLComponents(string: baseURL),
              let scheme = url.scheme?.lowercased(),
              ["http", "https"].contains(scheme),
              url.host != nil, url.user == nil, url.password == nil,
              url.query == nil, url.fragment == nil else {
            return "Enter a complete http(s) API base URL without a key or query string. / 请填写完整的 http(s) 服务地址，不要把密钥放入地址。"
        }
        if scheme == "http" && !isLocal && allowInsecureHTTP != true {
            return "Enable trusted HTTP for this internal API service. / 如为可信的内部服务，请明确启用 HTTP 连接。"
        }
        if model.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return "Enter the exact model ID supplied by your API service. / 请填写 API 服务提供的准确模型 ID。"
        }
        if apiKeyEnv.range(of: "^[A-Za-z_][A-Za-z0-9_]*$", options: .regularExpression) == nil {
            return "The imported API key variable name is invalid. / 导入配置中的密钥变量名无效。"
        }
        if !(1...600).contains(timeoutSeconds) || !(1_024...20_000_000).contains(maxResponseBytes) {
            return "The imported timeout or response limit is out of range. / 导入配置中的超时或响应大小超出允许范围。"
        }
        if !["system", "none", "custom"].contains(effectiveProxyMode) {
            return "Choose a valid network route. / 请选择有效的网络连接方式。"
        }
        if effectiveProxyMode == "custom" {
            guard let proxy = URLComponents(string: proxyURL),
                  let proxyScheme = proxy.scheme?.lowercased(),
                  ["http", "https"].contains(proxyScheme),
                  proxy.host != nil, proxy.user == nil, proxy.password == nil,
                  proxy.query == nil, proxy.fragment == nil else {
                return "Enter an http(s) proxy URL such as http://127.0.0.1:1082. / 请填写 http(s) 代理地址，例如 http://127.0.0.1:1082。"
            }
        }
        if !["chat_completions", "responses", "anthropic_messages"].contains(effectiveAPIMode) {
            return "Choose a supported API protocol. / 请选择支持的 API 协议。"
        }
        if !["auto", "stdlib", "sdk"].contains(effectiveTransportBackend) {
            return "Choose a supported request client. / 请选择支持的请求客户端。"
        }
        if let options = requestOptionsJSON, !options.isEmpty {
            guard let data = options.data(using: .utf8),
                  let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  Set(object.keys).isDisjoint(with: ["model", "messages", "input", "instructions", "system", "stream"]) else {
                return "Additional parameters must be a JSON object without core request fields. / 附加参数须为 JSON 对象，不能覆盖模型、消息或流式开关。"
            }
        }
        return nil
    }

    func temporaryFile() throws -> URL {
        let path = FileManager.default.temporaryDirectory
            .appendingPathComponent("dbabel-provider-\(UUID().uuidString).json")
        var configuration: [String: Any] = [
            "provider": "openai-compatible",
            "base_url": baseURL,
            "model": model,
            "api_key_env": apiKeyEnv,
            "timeout_seconds": timeoutSeconds,
            "max_response_bytes": maxResponseBytes,
            "allow_insecure_http": allowInsecureHTTP == true,
            "proxy_mode": effectiveProxyMode,
            "api_mode": effectiveAPIMode,
            "transport_backend": effectiveTransportBackend,
            "stream": stream ?? true,
            "temperature_mode": temperatureMode ?? "auto"
        ]
        if let maxOutputTokens { configuration["max_output_tokens"] = maxOutputTokens }
        if let options = requestOptionsJSON, !options.isEmpty,
           let bytes = options.data(using: .utf8) {
            configuration["extra_body"] = try JSONSerialization.jsonObject(with: bytes)
        }
        let data = try JSONSerialization.data(withJSONObject: configuration, options: [.prettyPrinted, .sortedKeys])
        try data.write(to: path, options: [.atomic])
        return path
    }
}

final class DesktopController {
    struct SavedSession {
        let bundle: URL
        let title: String
        let updated: Date
    }

    private var previousWorkspaces: [URL] {
        let support = FileManager.default.urls(for: .applicationSupportDirectory,
                                                in: .userDomainMask)[0]
            .appendingPathComponent("DBabel")
        let legacy = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("DBabel/output")
        var seen = Set<String>()
        return [workspace, support, legacy].filter {
            seen.insert($0.standardizedFileURL.path).inserted
        }
    }

    func savedSessions() -> [SavedSession] {
        let roots = previousWorkspaces.flatMap { base in
            [base.appendingPathComponent("runtime"),
             base.appendingPathComponent("dbabel-sessions"),
             base]
        }
        var found: [String: SavedSession] = [:]
        for root in roots {
            guard let entries = try? FileManager.default.contentsOfDirectory(
                at: root, includingPropertiesForKeys: [.contentModificationDateKey],
                options: [.skipsHiddenFiles]) else { continue }
            for entry in entries where entry.pathExtension == "dbreview" ||
                root.lastPathComponent != "DBabel" && root.lastPathComponent != "output" {
                let bundle = entry.pathExtension == "dbreview"
                    ? entry : entry.appendingPathComponent("review.dbreview")
                let session = bundle.appendingPathComponent("session.json")
                guard let bytes = try? Data(contentsOf: session),
                      let data = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any] else { continue }
                let key = data["session_id"] as? String ?? bundle.standardizedFileURL.path
                let title = data["title"] as? String ?? entry.lastPathComponent
                let updated = ["session.json", "decisions.json", "ui_state.json"].compactMap {
                    (try? bundle.appendingPathComponent($0).resourceValues(
                        forKeys: [.contentModificationDateKey]))?.contentModificationDate
                }.max() ?? .distantPast
                if let existing = found[key], existing.updated >= updated { continue }
                found[key] = SavedSession(bundle: bundle, title: title, updated: updated)
            }
        }
        return found.values.sorted { $0.updated > $1.updated }
    }

    private func rejectionMemorySnapshot() throws -> URL? {
        var records: [[String: Any]] = []
        var seen = Set<String>()
        for session in savedSessions() {
            let file = session.bundle.appendingPathComponent("rejected-translations.json")
            guard let bytes = try? Data(contentsOf: file),
                  let entries = try? JSONSerialization.jsonObject(with: bytes) as? [[String: Any]] else { continue }
            for entry in entries {
                guard let id = entry["id"] as? String else { continue }
                let scope = (entry["memory_scope"] as? [String: Any])?["key"] as? String
                let identity = (scope ?? session.bundle.path) + ":" + id
                guard seen.insert(identity).inserted else { continue }
                records.append(entry)
            }
        }
        guard !records.isEmpty else { return nil }
        try FileManager.default.createDirectory(at: workspace, withIntermediateDirectories: true)
        let destination = workspace.appendingPathComponent("rejected-translations.json")
        let payload = try JSONSerialization.data(withJSONObject: records, options: [.prettyPrinted, .sortedKeys])
        try payload.write(to: destination, options: [.atomic])
        return destination
    }

    struct ResumableRun {
        let root: URL
        let source: URL
        let sourceLanguage: String
        let targetLanguage: String
        let provider: [String: Any]
    }

    func resumableRuns() -> [ResumableRun] {
        var found: [ResumableRun] = []
        var seen = Set<String>()
        for directory in previousWorkspaces.map({ $0.appendingPathComponent("runtime") }) {
            let process = Process()
            let pipe = Pipe()
            process.executableURL = python
            process.arguments = [repository.appendingPathComponent("scripts/list_resumable_runs.py").path,
                                 "--workspace-root", directory.path]
            process.standardOutput = pipe
            process.standardError = FileHandle.nullDevice
            var env = ProcessInfo.processInfo.environment
            let vendor = bundledRepository != nil
                ? Bundle.main.resourceURL!.appendingPathComponent("vendor")
                : repository.appendingPathComponent("output/build-vendor")
            env["PYTHONPATH"] = [vendor.path, repository.path].joined(separator: ":")
            env["PYTHONNOUSERSITE"] = "1"
            process.environment = env
            do {
                try process.run()
                let bytes = pipe.fileHandleForReading.readDataToEndOfFile()
                process.waitUntilExit()
                guard process.terminationStatus == 0,
                      let rows = try JSONSerialization.jsonObject(with: bytes) as? [[String: Any]] else { continue }
                for value in rows {
                    guard let root = value["root"] as? String, seen.insert(root).inserted,
                          let path = value["source"] as? String,
                          let from = value["source_language"] as? String,
                          let to = value["target_language"] as? String,
                          let provider = value["provider"] as? [String: Any] else { continue }
                    found.append(ResumableRun(root: URL(fileURLWithPath: root),
                        source: URL(fileURLWithPath: path), sourceLanguage: from,
                        targetLanguage: to, provider: provider))
                }
            } catch { continue }
        }
        return found
    }
    var onStatus: (String) -> Void = { _ in }
    var onBusy: (Bool) -> Void = { _ in }
    var onWorkbench: (URL) -> Void = { _ in }
    var onProgress: ([String: Any]) -> Void = { _ in }
    var onTranslationFailure: (String) -> Void = { _ in }
    private var translationFailureDetails: [String: String] = [:]
    private var providerCheckDetails: [String: String] = [:]

    func lastTranslationFailureDetail(language: String) -> String? {
        translationFailureDetails[language.lowercased().hasPrefix("zh") ? "zh-CN" : "en"]
    }

    func lastProviderCheckDetail(language: String) -> String? {
        providerCheckDetails[language.lowercased().hasPrefix("zh") ? "zh-CN" : "en"]
    }

    func reportTranslationFailure(manifest: [String: Any]?, error: String,
                                  language: String, apiKey: String) {
        for selected in ["zh-CN", "en"] {
            translationFailureDetails[selected] = Self.translationFailureMessage(
                manifest: manifest, error: error, language: selected, secrets: [apiKey])
        }
        status = lastTranslationFailureDetail(language: language) ?? ""
        onTranslationFailure(status)
    }
    var workbenchURL: URL? { didSet { if let url = workbenchURL { onWorkbench(url) } } }
    var status = "" { didSet { onStatus(status) } }
    var busy = false { didSet { onBusy(busy) } }
    var lastBundle: URL?

    private var translationProcess: Process?
    private var server: Process?
    private var serverTimer: Timer?
    private var progressTimer: Timer?
    private var progressLineCount = 0

    private func readProgress(_ file: URL) {
        let lines = contents(file).split(whereSeparator: \.isNewline)
        guard lines.count > progressLineCount else { return }
        for line in lines.dropFirst(progressLineCount) {
            if let data = String(line).data(using: .utf8),
               let event = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                onProgress(event)
            }
        }
        progressLineCount = lines.count
    }

    private var bundledRepository: URL? {
        guard let resources = Bundle.main.resourceURL else { return nil }
        let root = resources.appendingPathComponent("DBabel")
        return FileManager.default.fileExists(
            atPath: root.appendingPathComponent("scripts/run_project.py").path
        ) ? root : nil
    }

    var repository: URL {
        if let override = ProcessInfo.processInfo.environment["DBABEL_REPO_ROOT"] {
            return URL(fileURLWithPath: override).standardizedFileURL
        }
        if let bundledRepository = bundledRepository { return bundledRepository }
        return Bundle.main.bundleURL
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
    }

    private var workspace: URL {
        guard bundledRepository != nil else {
            return repository.appendingPathComponent("output")
        }
        return FileManager.default.urls(for: .applicationSupportDirectory,
                                        in: .userDomainMask)[0]
            .appendingPathComponent("DBabel")
    }

    private var python: URL {
        if bundledRepository != nil, let resources = Bundle.main.resourceURL {
            return resources.appendingPathComponent("Python/bin/python3")
        }
        let built = repository.appendingPathComponent(
            "output/build-python/cpython-3.12.14-macos-aarch64-none/bin/python3")
        let vendor = repository.appendingPathComponent("output/build-vendor/yaml")
        if FileManager.default.isExecutableFile(atPath: built.path),
           FileManager.default.fileExists(atPath: vendor.path) { return built }
        let local = repository.appendingPathComponent(".venv/bin/python")
        if FileManager.default.isExecutableFile(atPath: local.path) { return local }
        return URL(fileURLWithPath: "/usr/bin/python3")
    }

    private func launch(_ arguments: [String], stdout: URL, stderr: URL,
                        environment: [String: String] = [:]) throws -> Process {
        let process = Process()
        process.executableURL = python
        process.arguments = arguments
        process.currentDirectoryURL = repository
        var processEnvironment = ProcessInfo.processInfo.environment.merging(environment) { _, new in new }
        if bundledRepository != nil, let resources = Bundle.main.resourceURL {
            processEnvironment["PYTHONPATH"] = [
                resources.appendingPathComponent("vendor").path,
                repository.path
            ].joined(separator: ":")
            processEnvironment["PYTHONNOUSERSITE"] = "1"
            processEnvironment["PYTHONDONTWRITEBYTECODE"] = "1"
        } else if python.path.contains("/output/build-python/") {
            processEnvironment["PYTHONPATH"] = [
                repository.appendingPathComponent("output/build-vendor").path,
                repository.path
            ].joined(separator: ":")
            processEnvironment["PYTHONNOUSERSITE"] = "1"
            processEnvironment["PYTHONDONTWRITEBYTECODE"] = "1"
        }
        process.environment = processEnvironment
        process.standardOutput = try FileHandle(forWritingTo: stdout)
        process.standardError = try FileHandle(forWritingTo: stderr)
        try process.run()
        return process
    }

    private func logFiles() throws -> (URL, URL) {
        let base = FileManager.default.temporaryDirectory
            .appendingPathComponent("dbabel-desktop-\(UUID().uuidString)")
        let output = base.appendingPathExtension("out")
        let error = base.appendingPathExtension("err")
        FileManager.default.createFile(atPath: output.path, contents: Data())
        FileManager.default.createFile(atPath: error.path, contents: Data())
        return (output, error)
    }

    private func contents(_ url: URL) -> String {
        (try? String(contentsOf: url, encoding: .utf8)) ?? ""
    }

    func openDemo() {
        var bundle = workspace.appendingPathComponent("local-demo.dbreview")
        if bundle == lastBundle, server?.isRunning == true, let url = workbenchURL {
            onWorkbench(url)
            return
        }
        if FileManager.default.fileExists(atPath: bundle.path), sessionIsLocked(bundle) {
            bundle = workspace.appendingPathComponent("dbabel-sessions")
                .appendingPathComponent("demo-\(UUID().uuidString).dbreview")
        }
        if !FileManager.default.fileExists(atPath: bundle.path) {
            do {
                try FileManager.default.createDirectory(
                    at: bundle.deletingLastPathComponent(),
                    withIntermediateDirectories: true
                )
                try FileManager.default.copyItem(
                    at: repository.appendingPathComponent("examples/review_workbench_demo.dbreview"),
                    to: bundle
                )
                if bundle.lastPathComponent != "local-demo.dbreview" {
                    let manifest = bundle.appendingPathComponent("session.json")
                    if let bytes = try? Data(contentsOf: manifest),
                       var data = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any] {
                        data["session_id"] = "RS_" + UUID().uuidString.lowercased()
                            .replacingOccurrences(of: "-", with: "")
                        try JSONSerialization.data(withJSONObject: data, options: [.prettyPrinted, .sortedKeys])
                            .write(to: manifest, options: [.atomic])
                    }
                }
            } catch {
                status = error.localizedDescription
                return
            }
        }
        openSession(bundle)
    }

    private func sessionIsLocked(_ bundle: URL) -> Bool {
        let descriptor = Darwin.open(bundle.appendingPathComponent(".workbench.lock").path,
                                     O_CREAT | O_RDWR, S_IRUSR | S_IWUSR)
        guard descriptor >= 0 else { return true }
        defer { Darwin.close(descriptor) }
        guard flock(descriptor, LOCK_EX | LOCK_NB) == 0 else { return true }
        flock(descriptor, LOCK_UN)
        return false
    }

    func createReviewSession(source: URL, target: URL?, from: String, to: String,
                             alignmentConfirmed: Bool) {
        guard FileManager.default.fileExists(atPath: source.path),
              target == nil || alignmentConfirmed else {
            status = "Choose a source and confirm existing-target alignment. / 请选择原文并确认现有译文的对齐。"
            return
        }
        busy = true
        status = "Inspecting documents and creating a review session… / 正在预检文档并建立审核会话…"
        do {
            let base = workspace.appendingPathComponent("dbabel-sessions")
            try FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
            let bundle = base.appendingPathComponent(UUID().uuidString + ".dbreview")
            let (output, error) = try logFiles()
            var arguments = [
                repository.appendingPathComponent("scripts/intake_document.py").path,
                source.path,
                "--source-language", from,
                "--target-languages", to,
                "--output", bundle.path
            ]
            if let target = target {
                arguments += ["--target", target.path, "--confirm-positional-alignment"]
            }
            let process = try launch(arguments, stdout: output, stderr: error)
            process.terminationHandler = { [weak self] finished in
                DispatchQueue.main.async {
                    guard let self = self else { return }
                    self.busy = false
                    if finished.terminationStatus == 0,
                       FileManager.default.fileExists(atPath: bundle.appendingPathComponent("session.json").path) {
                        self.openSession(bundle)
                    } else {
                        let detail = self.contents(error).trimmingCharacters(in: .whitespacesAndNewlines)
                        self.status = detail.isEmpty
                            ? "Document intake failed. / 文档上传和会话建立失败。" : detail
                    }
                }
            }
        } catch {
            busy = false
            status = error.localizedDescription
        }
    }

    func openSession(_ bundle: URL, original: URL? = nil) {
        translationFailureDetails = [:]
        guard bundle.pathExtension == "dbreview",
              FileManager.default.fileExists(atPath: bundle.path) else {
            status = "Choose an existing .dbreview session. / 请选择已有 .dbreview 会话。"
            onTranslationFailure(status)
            return
        }
        busy = true
        status = "Opening review session… / 正在打开审核会话…"
        startReviewServer(bundle, original: original)
    }

    private func startReviewServer(
        _ bundle: URL, original: URL?
    ) {
        do {
            let (output, error) = try logFiles()
            var exportOriginal = original
            let manifestPath = bundle.deletingLastPathComponent().appendingPathComponent("run.json")
            if exportOriginal == nil,
               let bytes = try? Data(contentsOf: manifestPath),
               let manifest = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any],
               let source = manifest["source"] as? [String: Any],
               let path = source["path"] as? String,
               FileManager.default.fileExists(atPath: path) {
                exportOriginal = URL(fileURLWithPath: path)
            }
            var arguments = [
                "-u", repository.appendingPathComponent("scripts/start_review_workbench.py").path,
                bundle.path, "--port", "0", "--no-browser"
            ]
            if let original = exportOriginal {
                let reviewed = bundle.deletingLastPathComponent()
                    .appendingPathComponent("reviewed-" + original.lastPathComponent)
                arguments += ["--original", original.path, "--output", reviewed.path]
            }
            let process = try launch(arguments, stdout: output, stderr: error)
            var attempts = 0
            serverTimer?.invalidate()
            serverTimer = Timer.scheduledTimer(withTimeInterval: 0.15, repeats: true) { [weak self] timer in
                guard let self = self else { timer.invalidate(); return }
                attempts += 1
                let line = self.contents(output).split(separator: "\n")
                    .first(where: { $0.hasPrefix("Open: ") })
                if let line = line,
                   let url = URL(string: String(line.dropFirst(6))) {
                    timer.invalidate()
                    self.server?.terminate()
                    self.server = process
                    self.lastBundle = bundle
                    self.workbenchURL = url
                    self.busy = false
                    self.status = ""
                    return
                }
                if !process.isRunning || attempts >= 100 {
                    timer.invalidate()
                    if process.isRunning { process.terminate() }
                    self.busy = false
                    self.status = self.contents(error).trimmingCharacters(in: .whitespacesAndNewlines)
                    if self.status.isEmpty { self.status = "Workbench failed to start. / 工作台启动失败。" }
                    self.onTranslationFailure(self.status)
                }
            }
        } catch {
            busy = false
            status = error.localizedDescription
            onTranslationFailure(status)
        }
    }

    func translate(source: URL, from: String, to: String, role: String,
                   provider: URL, apiKey: String, proxyURL: String = "",
                   temporaryProvider: Bool = false, resumeRun: URL? = nil,
                   language: String = "en") {
        translationFailureDetails = [:]
        guard FileManager.default.fileExists(atPath: source.path),
              FileManager.default.fileExists(atPath: provider.path),
              !from.trimmingCharacters(in: .whitespaces).isEmpty,
              !to.trimmingCharacters(in: .whitespaces).isEmpty,
              from.caseInsensitiveCompare(to) != .orderedSame,
              !role.trimmingCharacters(in: .whitespaces).isEmpty else {
            if temporaryProvider { try? FileManager.default.removeItem(at: provider) }
            status = "Select files and distinct languages. / 请选择文件和不同的原文、目标语言。"
            return
        }
        busy = true
        status = "Translating and checking… / 正在翻译并检查…"
        do {
            let (output, error) = try logFiles()
            let progress = FileManager.default.temporaryDirectory
                .appendingPathComponent("dbabel-progress-\(UUID().uuidString).jsonl")
            FileManager.default.createFile(atPath: progress.path, contents: Data())
            progressLineCount = 0
            var arguments = [
                repository.appendingPathComponent("scripts/run_project.py").path,
                source.path,
                "--source-language", from,
                "--target-language", to,
                "--text-role", role,
                "--provider-config", provider.path,
                "--workspace-root", (resumeRun?.deletingLastPathComponent()
                    ?? workspace.appendingPathComponent("runtime")).path,
                "--progress-jsonl", progress.path
            ]
            if let resumeRun = resumeRun {
                arguments += ["--resume-run", resumeRun.path]
            }
            var environment: [String: String] = [:]
            if !apiKey.isEmpty,
               let data = try? Data(contentsOf: provider),
               let configuration = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let variable = configuration["api_key_env"] as? String,
               variable.range(of: "^[A-Za-z_][A-Za-z0-9_]*$", options: .regularExpression) != nil {
                environment[variable] = apiKey
            }
            if !proxyURL.isEmpty {
                environment["HTTP_PROXY"] = proxyURL
                environment["HTTPS_PROXY"] = proxyURL
                environment["http_proxy"] = proxyURL
                environment["https_proxy"] = proxyURL
            }
            if let memory = try rejectionMemorySnapshot() {
                environment["DBABEL_REJECTION_MEMORY"] = memory.path
            }
            let process = try launch(arguments, stdout: output, stderr: error,
                                     environment: environment)
            translationProcess = process
            progressTimer?.invalidate()
            progressTimer = Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { [weak self] _ in
                self?.readProgress(progress)
            }
            process.terminationHandler = { [weak self] finished in
                DispatchQueue.main.async {
                    if temporaryProvider { try? FileManager.default.removeItem(at: provider) }
                    guard let self = self else { return }
                    self.translationProcess = nil
                    self.progressTimer?.invalidate()
                    self.progressTimer = nil
                    self.readProgress(progress)
                    try? FileManager.default.removeItem(at: progress)
                    self.busy = false
                    let manifest = self.contents(output).data(using: .utf8).flatMap {
                        try? JSONSerialization.jsonObject(with: $0) as? [String: Any]
                    }
                    if finished.terminationStatus == 0,
                       manifest?["status"] as? String == "READY_FOR_HUMAN_REVIEW",
                       let artifacts = manifest?["artifacts"] as? [String: Any],
                       let review = artifacts["review_bundle"] as? [String: Any],
                       let path = review["path"] as? String {
                        self.openSession(URL(fileURLWithPath: path), original: source)
                        return
                    }
                    self.reportTranslationFailure(manifest: manifest, error: self.contents(error),
                                                  language: language, apiKey: apiKey)
                }
            }
        } catch {
            if temporaryProvider { try? FileManager.default.removeItem(at: provider) }
            busy = false
            reportTranslationFailure(manifest: nil, error: error.localizedDescription,
                                     language: language, apiKey: apiKey)
        }
    }

    func checkProvider(provider: URL, apiKey: String, proxyURL: String = "",
                       language: String = "en",
                       onResult: @escaping (Bool, String) -> Void) {
        providerCheckDetails = [:]
        do {
            let (output, error) = try logFiles()
            var environment: [String: String] = [:]
            if !apiKey.isEmpty,
               let data = try? Data(contentsOf: provider),
               let configuration = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let variable = configuration["api_key_env"] as? String {
                environment[variable] = apiKey
            }
            if !proxyURL.isEmpty {
                environment["HTTP_PROXY"] = proxyURL
                environment["HTTPS_PROXY"] = proxyURL
                environment["http_proxy"] = proxyURL
                environment["https_proxy"] = proxyURL
            }
            let script = repository.appendingPathComponent("scripts/check_provider_connection.py")
            let process = try launch([script.path, "--provider-config", provider.path, "--task-check"],
                                     stdout: output, stderr: error,
                                     environment: environment)
            process.terminationHandler = { [weak self] finished in
                DispatchQueue.main.async {
                    try? FileManager.default.removeItem(at: provider)
                    guard let self = self else { return }
                    let outputText = self.contents(output)
                    let errorText = self.contents(error)
                    for selected in ["zh-CN", "en"] {
                        self.providerCheckDetails[selected] = Self.providerCheckResult(
                            exitStatus: finished.terminationStatus, output: outputText,
                            error: errorText, language: selected, secrets: [apiKey]).detail
                    }
                    let result = Self.providerCheckResult(exitStatus: finished.terminationStatus,
                                                          output: outputText,
                                                          error: errorText, language: language,
                                                          secrets: [apiKey])
                    onResult(result.success, result.detail)
                }
            }
        } catch {
            try? FileManager.default.removeItem(at: provider)
            onResult(false, Self.safeErrorText(error.localizedDescription, limit: 6_000, secrets: [apiKey]))
        }
    }

    static func providerCheckResult(exitStatus: Int32, output: String,
                                    error: String, language: String = "en",
                                    secrets: [String] = []) -> (success: Bool, detail: String) {
        let chinese = language.lowercased().hasPrefix("zh")
        if let bytes = output.data(using: .utf8),
           let report = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any] {
            if exitStatus == 0, report["status"] as? String == "TASK_READY",
               report["contract_verified"] as? Bool == true {
                return (true, chinese ? "样本翻译检查通过。" : "Sample translation check passed.")
            }
            if let failure = report["error"] as? [String: Any] {
                return (false, providerErrorMessage(failure, language: language, secrets: secrets))
            }
            if report["status"] as? String == "CONTRACT_FAILED" {
                let findings = (report["findings"] as? [String] ?? []).prefix(20).joined(separator: "\n")
                return (false, providerErrorMessage([
                    "type": "CONTRACT_FAILED", "title_zh": "样本翻译检查未通过", "title_en": "Sample translation check failed",
                    "explanation_zh": "API 已连接；返回的翻译格式或技术字面量未通过检查。",
                    "explanation_en": "API connected; the translation format or technical literals failed validation.",
                    "actions_zh": ["核对接口协议与模型，确认它支持按要求返回翻译 JSON。", "检查下方详情，调整配置后重新测试。"],
                    "actions_en": ["Check the API protocol and model support for the required translation JSON.", "Review the details below, adjust the configuration, then test again."],
                    "service_message": findings], language: language, secrets: secrets))
            }
        }
        let detail = safeErrorText(error, limit: 6_000, secrets: secrets)
        return (false, detail.isEmpty
            ? (chinese ? "API 测试未返回有效的任务结果。请核对服务配置后重新测试。"
                       : "The API test returned no valid task result. Check the service configuration, then test again.")
            : (chinese ? "API 测试失败\n\n错误详情\n" : "API test failed\n\nError details\n") + detail
                + (chinese ? "\n\n操作步骤\n核对服务地址、模型、密钥和网络路由，调整后重新测试。"
                           : "\n\nNext steps\nCheck the service URL, model, key and network route, then test again."))
    }

    static func safeErrorText(_ value: String, limit: Int, secrets: [String] = []) -> String {
        var text = value
        for secret in secrets where !secret.isEmpty {
            text = text.replacingOccurrences(of: secret, with: "[REDACTED]")
        }
        for (pattern, replacement) in [
            (#"(?i)\bBearer\s+[^\s,;\"']+"#, "Bearer [REDACTED]"),
            (#"(?i)\b(api[_-]?key|authorization|access[_-]?token|password|secret)\b([\"']?\s*[:=]\s*[\"']?)[^\s,\"';}]+"#, "$1$2[REDACTED]"),
            (#"(?i)(https?://)[^/\s@]+@"#, "$1[REDACTED]@"),
            (#"\b(?:sk|rk|pk)-[A-Za-z0-9_-]{8,}\b"#, "[REDACTED]")
        ] {
            if let expression = try? NSRegularExpression(pattern: pattern) {
                text = expression.stringByReplacingMatches(in: text,
                    range: NSRange(text.startIndex..., in: text), withTemplate: replacement)
            }
        }
        text = String(String.UnicodeScalarView(text.unicodeScalars.filter {
            $0.value >= 32 || $0.value == 10 || $0.value == 9
        })).trimmingCharacters(in: .whitespacesAndNewlines)
        return text.count > limit ? String(text.prefix(limit)) + "\n…" : text
    }

    static func providerErrorMessage(_ report: [String: Any], language: String = "en",
                                     secrets: [String] = []) -> String {
        let chinese = language.lowercased().hasPrefix("zh")
        func local(_ zh: String, _ en: String) -> String { chinese ? zh : en }
        func value(_ key: String, limit: Int = 2_000) -> String {
            safeErrorText(report[key] as? String ?? "", limit: limit, secrets: secrets)
        }
        func localized(_ key: String, limit: Int = 2_000) -> String {
            let selected = value(key + (chinese ? "_zh" : "_en"), limit: limit)
            return selected.isEmpty ? value(key + (chinese ? "_en" : "_zh"), limit: limit) : selected
        }
        let type = value("type", limit: 100)
        let title = localized("title", limit: 250)
        var sections = [local("错误类型：", "Error type: ")
                        + (title.isEmpty ? local("API 请求失败", "API request failed") : title)
                        + (type.isEmpty ? "" : " (\(type))")]
        let explanation = localized("explanation")
        if !explanation.isEmpty { sections.append(local("原因\n", "Reason\n") + explanation) }
        let selectedActions = report[chinese ? "actions_zh" : "actions_en"] as? [String] ?? []
        let alternateActions = report[chinese ? "actions_en" : "actions_zh"] as? [String] ?? []
        let actions = (selectedActions.isEmpty ? alternateActions : selectedActions).prefix(10)
            .map { safeErrorText($0, limit: 900, secrets: secrets) }.filter { !$0.isEmpty }
        if !actions.isEmpty {
            sections.append(local("操作步骤\n", "Next steps\n") + actions.enumerated()
                .map { "\($0.offset + 1). \($0.element)" }.joined(separator: "\n"))
        }
        var service = [String]()
        if let code = report["http_status"] as? Int, (100...599).contains(code) { service.append("HTTP \(code)") }
        let message = value("service_message", limit: 4_000)
        if !message.isEmpty { service.append(message) }
        if !service.isEmpty {
            let heading = type == "CONTRACT_FAILED" ? local("检查详情\n", "Check details\n") : local("服务原文\n", "Service response\n")
            sections.append(heading + service.joined(separator: "\n"))
        }
        var diagnostics = [String]()
        for (key, zh, en, limit) in [("request_id", "请求 ID", "Request ID", 200),
                                    ("backend", "请求客户端", "Request client", 150),
                                    ("route", "网络路由", "Network route", 500)] {
            let item = value(key, limit: limit)
            if !item.isEmpty { diagnostics.append(local(zh, en) + ": " + item) }
        }
        if let attempts = report["attempts"] as? Int, attempts >= 0 {
            diagnostics.append(local("尝试次数", "Attempts") + ": \(min(attempts, 10_000))")
        }
        if !diagnostics.isEmpty { sections.append(local("诊断信息\n", "Diagnostics\n") + diagnostics.joined(separator: "\n")) }
        return safeErrorText(sections.joined(separator: "\n\n"), limit: 18_000, secrets: secrets)
    }

    static func translationFailureMessage(manifest: [String: Any]?, error: String,
                                          language: String = "en", secrets: [String] = []) -> String {
        let chinese = language.lowercased().hasPrefix("zh")
        if let failure = manifest?["failure"] as? [String: Any] {
            if let report = failure["provider_error"] as? [String: Any] {
                return providerErrorMessage(report, language: language, secrets: secrets)
            }
            let reason = safeErrorText(failure["reason"] as? String ?? "", limit: 6_000, secrets: secrets)
            if !reason.isEmpty {
                let stage = safeErrorText(failure["stage"] as? String ?? "", limit: 100, secrets: secrets)
                let heading = stage == "FORMAT_PROBE"
                    ? (chinese ? "文档预检未通过，尚未调用翻译 API。" : "Document preflight stopped before API translation.")
                    : (chinese ? "翻译停在 \(stage) 阶段。" : "Translation stopped at \(stage).")
                return heading + "\n\n" + reason
            }
        }
        if let report = manifest?["error"] as? [String: Any] {
            return providerErrorMessage(report, language: language, secrets: secrets)
        }
        let detail = safeErrorText(error, limit: 6_000, secrets: secrets)
        return detail.isEmpty
            ? (chinese ? "翻译未进入人工审核。请查看运行记录中的错误详情，调整后继续本次运行。"
                       : "Translation stopped before human review. Inspect the run report, make the suggested changes, then resume this run.")
            : (chinese ? "翻译未完成\n\n错误详情\n" : "Translation did not complete\n\nError details\n") + detail
                + (chinese ? "\n\n操作步骤\n查看可用运行记录，核对文件和 API 配置，调整后重试。"
                           : "\n\nNext steps\nInspect the available run report, check the document and API configuration, then retry.")
    }

    func close() {
        serverTimer?.invalidate()
        translationProcess?.terminate()
        server?.terminate()
    }
}

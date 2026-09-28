import AppKit
import Foundation
import WebKit
import UniformTypeIdentifiers

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

final class DesktopController {
    struct SavedSession {
        let bundle: URL
        let title: String
        let updated: Date
    }

    func savedSessions() -> [SavedSession] {
        let roots = [workspace.appendingPathComponent("runtime"),
                     workspace.appendingPathComponent("dbabel-sessions")]
        var found: [SavedSession] = []
        for root in roots {
            guard let entries = try? FileManager.default.contentsOfDirectory(
                at: root, includingPropertiesForKeys: [.contentModificationDateKey],
                options: [.skipsHiddenFiles]) else { continue }
            for entry in entries {
                let bundle = entry.pathExtension == "dbreview"
                    ? entry : entry.appendingPathComponent("review.dbreview")
                let session = bundle.appendingPathComponent("session.json")
                guard let bytes = try? Data(contentsOf: session),
                      let data = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any] else { continue }
                let title = data["title"] as? String ?? entry.lastPathComponent
                let updated = (try? session.resourceValues(forKeys: [.contentModificationDateKey]))?
                    .contentModificationDate ?? .distantPast
                found.append(SavedSession(bundle: bundle, title: title, updated: updated))
            }
        }
        return found.sorted { $0.updated > $1.updated }
    }

    private func rejectionMemorySnapshot() throws -> URL? {
        var records: [[String: Any]] = []
        var seen = Set<String>()
        for session in savedSessions() {
            let file = session.bundle.appendingPathComponent("rejected-translations.json")
            guard let bytes = try? Data(contentsOf: file),
                  let entries = try? JSONSerialization.jsonObject(with: bytes) as? [[String: Any]] else { continue }
            for entry in entries {
                guard let id = entry["id"] as? String, !seen.contains(id) else { continue }
                seen.insert(id)
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
        let directory = workspace.appendingPathComponent("runtime")
        guard let runs = try? FileManager.default.contentsOfDirectory(
            at: directory, includingPropertiesForKeys: [.contentModificationDateKey],
            options: [.skipsHiddenFiles]) else { return [] }
        var found: [ResumableRun] = []
        for root in runs.sorted(by: {
            let left = (try? $0.appendingPathComponent("run.json").resourceValues(
                forKeys: [.contentModificationDateKey]))?.contentModificationDate ?? .distantPast
            let right = (try? $1.appendingPathComponent("run.json").resourceValues(
                forKeys: [.contentModificationDateKey]))?.contentModificationDate ?? .distantPast
            return left > right
        }) where root.lastPathComponent.hasPrefix("RUN_") {
            let manifest = root.appendingPathComponent("run.json")
            guard let bytes = try? Data(contentsOf: manifest),
                  let value = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any],
                  value["mode"] as? String == "TRANSLATE",
                  value["status"] as? String == "FAILED",
                  let source = value["source"] as? [String: Any],
                  let path = source["path"] as? String,
                  FileManager.default.fileExists(atPath: path),
                  let from = value["source_language"] as? String,
                  let to = value["target_language"] as? String,
                  let provider = value["provider"] as? [String: Any],
                  let artifacts = value["artifacts"] as? [String: Any],
                  artifacts["ingest"] != nil else { continue }
            found.append(ResumableRun(root: root, source: URL(fileURLWithPath: path),
                                      sourceLanguage: from, targetLanguage: to, provider: provider))
        }
        return found
    }
    var onStatus: (String) -> Void = { _ in }
    var onBusy: (Bool) -> Void = { _ in }
    var onWorkbench: (URL) -> Void = { _ in }
    var onProgress: ([String: Any]) -> Void = { _ in }
    var onTranslationFailure: (String) -> Void = { _ in }
    var chatProvider: () -> (config: URL, keyName: String, key: String)? = { nil }
    var workbenchURL: URL? { didSet { if let url = workbenchURL { onWorkbench(url) } } }
    var status = "" { didSet { onStatus(status) } }
    var busy = false { didSet { onBusy(busy) } }
    var lastBundle: URL?

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
        let bundle = workspace.appendingPathComponent("local-demo.dbreview")
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
            } catch {
                status = error.localizedDescription
                return
            }
        }
        openSession(bundle)
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
        guard bundle.pathExtension == "dbreview",
              FileManager.default.fileExists(atPath: bundle.path) else {
            status = "Choose an existing .dbreview session. / 请选择已有 .dbreview 会话。"
            onTranslationFailure(status)
            return
        }
        busy = true
        status = "Opening review session… / 正在打开审核会话…"
        let provider = chatProvider
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let chat = provider()
            DispatchQueue.main.async { [weak self] in
                self?.startReviewServer(bundle, original: original, chat: chat)
            }
        }
    }

    private func startReviewServer(
        _ bundle: URL, original: URL?,
        chat: (config: URL, keyName: String, key: String)?
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
            if let chat = chat {
                arguments += ["--provider-config", chat.config.path]
            }
            if let original = exportOriginal {
                let reviewed = bundle.deletingLastPathComponent()
                    .appendingPathComponent("reviewed-" + original.lastPathComponent)
                arguments += ["--original", original.path, "--output", reviewed.path]
            }
            let chatEnvironment = chat.map { [$0.keyName: $0.key] } ?? [:]
            let process = try launch(arguments, stdout: output, stderr: error,
                                     environment: chatEnvironment)
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
                    if let chat = chat { try? FileManager.default.removeItem(at: chat.config) }
                    self.server?.terminate()
                    self.server = process
                    self.workbenchURL = url
                    self.lastBundle = bundle
                    self.busy = false
                    self.status = ""
                    return
                }
                if !process.isRunning || attempts >= 100 {
                    timer.invalidate()
                    if let chat = chat { try? FileManager.default.removeItem(at: chat.config) }
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
                   temporaryProvider: Bool = false, resumeRun: URL? = nil) {
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
                "--workspace-root", workspace.appendingPathComponent("runtime").path,
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
            progressTimer?.invalidate()
            progressTimer = Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { [weak self] _ in
                self?.readProgress(progress)
            }
            process.terminationHandler = { [weak self] finished in
                DispatchQueue.main.async {
                    if temporaryProvider { try? FileManager.default.removeItem(at: provider) }
                    guard let self = self else { return }
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
                    if let failure = manifest?["failure"] as? [String: Any],
                       let stage = failure["stage"] as? String,
                       let reason = failure["reason"] as? String {
                        let heading = stage == "FORMAT_PROBE"
                            ? "Document preflight stopped before API translation. / 文档预检未通过，尚未调用翻译 API。"
                            : "Translation stopped at \(stage). / 翻译停在 \(stage) 阶段。"
                        self.status = heading + "\n" + String(reason.prefix(600))
                        self.onTranslationFailure(self.status)
                        return
                    }
                    let detail = self.contents(error).trimmingCharacters(in: .whitespacesAndNewlines)
                    self.status = detail.isEmpty
                        ? "Translation stopped before human review; inspect the run report. / 翻译未进入人工审核，请检查运行记录。"
                        : detail
                    self.onTranslationFailure(self.status)
                }
            }
        } catch {
            if temporaryProvider { try? FileManager.default.removeItem(at: provider) }
            busy = false
            status = error.localizedDescription
            onTranslationFailure(status)
        }
    }

    func checkProvider(provider: URL, apiKey: String, proxyURL: String = "",
                       onResult: @escaping (Bool, String) -> Void) {
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
            let process = try launch([script.path, "--provider-config", provider.path],
                                     stdout: output, stderr: error,
                                     environment: environment)
            process.terminationHandler = { [weak self] finished in
                DispatchQueue.main.async {
                    try? FileManager.default.removeItem(at: provider)
                    guard let self = self else { return }
                    if finished.terminationStatus == 0 {
                        onResult(true, self.contents(output))
                    } else {
                        onResult(false, self.contents(error))
                    }
                }
            }
        } catch {
            try? FileManager.default.removeItem(at: provider)
            onResult(false, error.localizedDescription)
        }
    }

    func close() {
        serverTimer?.invalidate()
        server?.terminate()
    }
}

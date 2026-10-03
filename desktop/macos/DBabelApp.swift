import AppKit
import Foundation
import Security
import UniformTypeIdentifiers
import WebKit

private final class FlippedView: NSView {
    override var isFlipped: Bool { true }
}

private final class ResponsiveSessionGrid: NSView {
    override var isFlipped: Bool { true }

    private var cards: [NSView] = []
    private let gap: CGFloat = 16
    private let minimumCardWidth: CGFloat = 280
    private let cardHeight: CGFloat = 250
    private var heightConstraint: NSLayoutConstraint?

    func install(_ views: [NSView]) {
        cards = views
        views.forEach(addSubview)
        heightConstraint = heightAnchor.constraint(equalToConstant: cardHeight)
        heightConstraint?.isActive = true
    }

    override func layout() {
        super.layout()
        let width = max(bounds.width, minimumCardWidth)
        let columns = max(1, Int((width + gap) / (minimumCardWidth + gap)))
        let cardWidth = (width - CGFloat(columns - 1) * gap) / CGFloat(columns)
        for (index, card) in cards.enumerated() {
            let column = index % columns
            let row = index / columns
            card.frame = NSRect(x: CGFloat(column) * (cardWidth + gap),
                                y: CGFloat(row) * (cardHeight + gap),
                                width: cardWidth, height: cardHeight)
        }
        let rows = (cards.count + columns - 1) / columns
        let height = CGFloat(rows) * cardHeight + CGFloat(max(rows - 1, 0)) * gap
        if abs((heightConstraint?.constant ?? 0) - height) > 0.5 {
            heightConstraint?.constant = height
        }
    }
}

private final class MaterialWebView: WKWebView {
    override var isOpaque: Bool { false }

    func allowWindowMaterialToShowThrough() {
        underPageBackgroundColor = .clear
        // AppKit's opacity hint and under-page color do not disable WebKit's
        // separate page canvas on macOS. Use WebKit's optional selector when
        // present; keep the normal canvas on systems where it is unavailable.
        let selector = NSSelectorFromString("_setDrawsBackground:")
        guard responds(to: selector) else { return }
        typealias Setter = @convention(c) (AnyObject, Selector, Bool) -> Void
        let setDrawsBackground = unsafeBitCast(method(for: selector), to: Setter.self)
        setDrawsBackground(self, selector, false)
    }
}

private struct ProviderSettings: Codable {
    let baseURL: String
    let model: String
    let apiKeyEnv: String
    let proxyURL: String
    let timeoutSeconds: Int
    let maxResponseBytes: Int
    let allowInsecureHTTP: Bool?
    let proxyMode: String?
    let apiMode: String?
    let stream: Bool?
    let temperatureMode: String?
    let maxOutputTokens: Int?
    let requestOptionsJSON: String?

    var effectiveAPIMode: String { apiMode ?? "chat_completions" }

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

private enum ProviderCredentialStore {
    private static let service = "org.dbabel.desktop.api-key"

    static func key(for baseURL: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: baseURL,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]
        var result: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    static func save(_ key: String, for baseURL: String) -> OSStatus {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: baseURL
        ]
        let value: [String: Any] = [kSecValueData as String: Data(key.utf8)]
        let status = SecItemAdd(query.merging(value) { _, new in new } as CFDictionary, nil)
        if status == errSecDuplicateItem {
            return SecItemUpdate(query as CFDictionary, value as CFDictionary)
        }
        return status
    }
}

private enum DesktopAppearance: String {
    case system, light, dark
}

private struct APIServicePreset {
    let title: String
    let baseURL: String
    let models: [String]
}

// These are editable starting points. Availability and model access are checked
// by the real Chat Completions test request before the user starts a project.
private let apiServicePresets: [APIServicePreset] = [
    .init(title: "DeepSeek", baseURL: "https://api.deepseek.com",
          models: ["deepseek-v4-flash", "deepseek-v4-pro"]),
    .init(title: "OpenAI", baseURL: "https://api.openai.com/v1",
          models: ["gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini"]),
    .init(title: "Google Gemini", baseURL: "https://generativelanguage.googleapis.com/v1beta/openai",
          models: ["gemini-3.8-flash", "gemini-3.5-flash"]),
    .init(title: "Kimi / Moonshot (global)", baseURL: "https://api.moonshot.ai/v1",
          models: ["kimi-k2.5"]),
    .init(title: "Kimi / Moonshot (中国)", baseURL: "https://api.moonshot.cn/v1",
          models: ["kimi-k2.5"]),
    .init(title: "Claude (compatibility)", baseURL: "https://api.anthropic.com/v1",
          models: ["claude-sonnet-4-6"]),
    .init(title: "xAI", baseURL: "https://api.x.ai/v1",
          models: ["grok-4.7", "grok-4.6"]),
    .init(title: "阿里云百炼 / Qwen (北京)", baseURL: "https://dashscope.aliyuncs.com/compatible-mode/v1",
          models: ["qwen-plus"])
]

final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, NSToolbarDelegate, WKNavigationDelegate,
                         WKUIDelegate, WKDownloadDelegate {
    private let desktop = DesktopController()
    private var window: NSWindow!
    private var root: NSView!
    private var windowMaterial: NSVisualEffectView!
    private var closingAfterSave = false
    private var body: NSView!
    private var browser: WKWebView?
    private var currentURL: URL?
    private var source: URL?
    private var pendingResume: DesktopController.ResumableRun?
    private var existingTarget: URL?
    private var providerSettings: ProviderSettings?
    private var pendingApiKeyEnv = "DBABEL_API_KEY"
    private var pendingTimeout = 120
    private var pendingMaxBytes = 2_000_000
    private var homeFieldConstraintsSet = false
    private var providerFieldConstraintsSet = false
    private var providerSheet: NSPanel?
    private enum LandingPage { case welcome, translate, localReview, history, progress, workbench }
    private var landingPage: LandingPage = .welcome
    private var recentAPIKey: String?
    private var recentAPIKeyBaseURL: String?
    private var apiTestButton: NSButton?
    private var appearance: DesktopAppearance = .system
    private var chinese = true
    private var controls: [NSButton] = []
    private var progressPageActive = false
    private var progressLastEvent: [String: Any]?
    private var progressSteps: [NSTextField] = []
    private let progressHeading = NSTextField(labelWithString: "")
    private let progressDocument = NSTextField(labelWithString: "")
    private let progressDetail = NSTextField(wrappingLabelWithString: "")
    private let progressUnit = NSTextField(labelWithString: "")
    private let progressSource = NSTextField(wrappingLabelWithString: "")
    private let progressBar = NSProgressIndicator()
    private let status = NSTextField(labelWithString: "")
    private let sourceName = NSTextField(labelWithString: "")
    private let targetName = NSTextField(labelWithString: "")
    private let alignmentConfirmed = NSButton(checkboxWithTitle: "", target: nil, action: nil)
    private let providerName = NSTextField(labelWithString: "")
    private let apiBaseURL = NSTextField(string: "")
    private let apiModel = NSTextField(string: "")
    private let apiProviderPreset = NSPopUpButton()
    private let apiModelPreset = NSPopUpButton()
    private let apiProtocol = NSPopUpButton()
    private let apiStream = NSButton(checkboxWithTitle: "", target: nil, action: nil)
    private let apiOmitTemperature = NSButton(checkboxWithTitle: "", target: nil, action: nil)
    private let apiTimeout = NSTextField(string: "300")
    private let apiOptions = NSTextField(string: "")
    private var pendingMaxTokens: Int?
    private let apiProxy = NSTextField(string: "")
    private let apiProxyMode = NSPopUpButton(frame: .zero, pullsDown: false)
    private let apiTrustedHTTP = NSButton(checkboxWithTitle: "", target: nil, action: nil)
    private let apiStatus = NSTextField(labelWithString: "")
    private let from = NSPopUpButton(frame: .zero, pullsDown: false)
    private let to = NSPopUpButton(frame: .zero, pullsDown: false)
    private let role = NSTextField(string: "PROSE")
    private let apiKey = NSSecureTextField(string: "")
    private let languageChoices: [(String, String)] = [
        ("zh-CN", "简体中文 · zh-CN"), ("zh-TW", "繁體中文 · zh-TW"),
        ("zh-HK", "香港繁體中文 · zh-HK"), ("en", "English · en"),
        ("en-US", "English (US) · en-US"), ("en-GB", "English (UK) · en-GB"),
        ("ja", "日本語 · ja"), ("ko", "한국어 · ko"),
        ("de", "Deutsch · de"), ("fr", "Français · fr"),
        ("es", "Español · es"), ("pt-BR", "Português (Brasil) · pt-BR"),
        ("pt-PT", "Português (Portugal) · pt-PT"), ("it", "Italiano · it"),
        ("ru", "Русский · ru"), ("ar", "العربية · ar"),
        ("hi", "हिन्दी · hi"), ("th", "ไทย · th"),
        ("vi", "Tiếng Việt · vi"), ("id", "Bahasa Indonesia · id"),
        ("ms", "Bahasa Melayu · ms"), ("tr", "Türkçe · tr"),
        ("nl", "Nederlands · nl"), ("pl", "Polski · pl"),
        ("uk", "Українська · uk"), ("sv", "Svenska · sv"),
        ("da", "Dansk · da"), ("fi", "Suomi · fi"),
        ("nb", "Norsk bokmål · nb"), ("he", "עברית · he")
    ]

    private func local(_ zh: String, _ en: String) -> String { chinese ? zh : en }

    private func configureLanguageMenus() {
        for menu in [from, to] {
            menu.removeAllItems()
            for (code, title) in languageChoices {
                menu.addItem(withTitle: title)
                menu.lastItem?.representedObject = code
            }
        }
        from.selectItem(at: 0)
        to.selectItem(at: 3)
    }

    private func languageCode(_ menu: NSPopUpButton) -> String {
        menu.selectedItem?.representedObject as? String ?? ""
    }

    private func languagesAreValid() -> Bool {
        let sourceLanguage = languageCode(from)
        let targetLanguage = languageCode(to)
        guard !sourceLanguage.isEmpty, !targetLanguage.isEmpty,
              sourceLanguage != targetLanguage else {
            status.stringValue = local("请选择不同的原文和目标语言。",
                                       "Choose different source and target languages.")
            return false
        }
        return true
    }

    private func matchingResumeRun() -> DesktopController.ResumableRun? {
        guard let settings = providerSettings else { return nil }
        return desktop.resumableRuns().first { run in
            run.provider["base_url"] as? String == settings.baseURL &&
            run.provider["model"] as? String == settings.model &&
            run.provider["api_key_env"] as? String == settings.apiKeyEnv &&
            (run.provider["api_mode"] as? String ?? "chat_completions") == settings.effectiveAPIMode
        }
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1120, height: 760),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = "DBabel"
        window.center()
        window.styleMask.insert(.fullSizeContentView)
        window.isOpaque = false
        window.backgroundColor = .clear
        window.titleVisibility = .hidden
        window.titlebarAppearsTransparent = true
        window.titlebarSeparatorStyle = .none
        window.toolbarStyle = .unified
        window.delegate = self
        let toolbar = NSToolbar(identifier: "DBabelToolbar")
        toolbar.delegate = self
        toolbar.displayMode = .iconOnly
        window.toolbar = toolbar
        buildMenus()
        let material = NSVisualEffectView(frame: window.contentView!.bounds)
        material.material = .underWindowBackground
        material.blendingMode = .behindWindow
        material.state = .active
        windowMaterial = material
        root = material
        window.contentView = root
        buildChrome()
        configureLanguageMenus()
        if let data = UserDefaults.standard.data(forKey: "DBabelProviderSettings.v1"),
           let saved = try? JSONDecoder().decode(ProviderSettings.self, from: data),
           saved.validationError() == nil {
            providerSettings = saved
        }
        showWelcome()
        desktop.onStatus = { [weak self] text in self?.status.stringValue = text }
        desktop.onBusy = { [weak self] busy in
            self?.controls.forEach { $0.isEnabled = !busy }
        }
        desktop.onWorkbench = { [weak self] url in
            guard let self else { return }
            self.showWorkbench(url)
            let name = self.desktop.lastBundle?.lastPathComponent ?? ""
            let isDemo = name == "local-demo.dbreview" ||
                (name.hasPrefix("demo-") && name.hasSuffix(".dbreview"))
            if !isDemo, let settings = self.providerSettings {
                self.updateCurrentWorkbenchChat(settings)
            }
        }
        desktop.onProgress = { [weak self] event in self?.updateProgress(event) }
        desktop.onTranslationFailure = { [weak self] message in self?.showProgressFailure(message) }
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationWillTerminate(_ notification: Notification) { desktop.close() }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard !closingAfterSave, landingPage == .workbench, browser != nil else { return .terminateNow }
        leaveWorkbench { saved in
            if saved { self.closingAfterSave = true }
            sender.reply(toApplicationShouldTerminate: saved)
        }
        return .terminateLater
    }

    func windowShouldClose(_ sender: NSWindow) -> Bool {
        guard !closingAfterSave, landingPage == .workbench, browser != nil else { return true }
        leaveWorkbench { saved in
            if saved {
                self.closingAfterSave = true
                sender.close()
            }
        }
        return false
    }

    func windowDidEnterFullScreen(_ notification: Notification) {
        windowMaterial.material = .underWindowBackground
        windowMaterial.blendingMode = .behindWindow
        window.backgroundColor = .clear
    }

    func windowDidExitFullScreen(_ notification: Notification) {
        windowMaterial.material = .underWindowBackground
        windowMaterial.blendingMode = .behindWindow
        window.backgroundColor = .clear
    }

    private let homeItem = NSToolbarItem.Identifier("DBabelHome")
    private let providerItem = NSToolbarItem.Identifier("DBabelProvider")
    private let appearanceItem = NSToolbarItem.Identifier("DBabelAppearance")
    private let languageItem = NSToolbarItem.Identifier("DBabelLanguage")
    private let pauseItem = NSToolbarItem.Identifier("DBabelPause")

    func toolbarDefaultItemIdentifiers(_ toolbar: NSToolbar) -> [NSToolbarItem.Identifier] {
        [providerItem, .flexibleSpace, pauseItem, homeItem, appearanceItem, languageItem]
    }

    func toolbarAllowedItemIdentifiers(_ toolbar: NSToolbar) -> [NSToolbarItem.Identifier] {
        [providerItem, .flexibleSpace, pauseItem, homeItem, appearanceItem, languageItem]
    }

    func toolbar(_ toolbar: NSToolbar, itemForItemIdentifier identifier: NSToolbarItem.Identifier,
                 willBeInsertedIntoToolbar flag: Bool) -> NSToolbarItem? {
        if identifier == appearanceItem {
            let item = NSToolbarItem(itemIdentifier: identifier)
            item.isBordered = false
            item.label = local("外观", "Appearance")
            item.image = NSImage(systemSymbolName: "circle.lefthalf.filled",
                                 accessibilityDescription: item.label)
            item.target = self
            item.action = #selector(appearanceToggleAction)
            return item
        }
        let item = NSToolbarItem(itemIdentifier: identifier)
        item.isBordered = false
        item.target = self
        if identifier == homeItem {
            item.label = local("首页", "Home")
            item.image = NSImage(systemSymbolName: "house", accessibilityDescription: item.label)
            item.action = #selector(homeAction)
        } else if identifier == providerItem {
            item.label = local("API 服务", "API Service")
            item.image = NSImage(systemSymbolName: "network", accessibilityDescription: item.label)
            item.action = #selector(providerAction)
        } else if identifier == languageItem {
            item.label = local("语言", "Language")
            item.image = NSImage(systemSymbolName: "globe", accessibilityDescription: item.label)
            item.action = #selector(languageAction)
        } else if identifier == pauseItem {
            item.label = local("暂存并返回", "Save and return")
            item.image = NSImage(systemSymbolName: "square.and.arrow.down", accessibilityDescription: item.label)
            item.action = #selector(pauseAction)
        } else { return nil }
        return item
    }

    private func buildMenus() {
        let menu = NSMenu()
        let app = NSMenuItem()
        let appMenu = NSMenu(title: "DBabel")
        appMenu.addItem(withTitle: local("关于 DBabel", "About DBabel"),
                            action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: local("退出 DBabel", "Quit DBabel"),
                            action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        app.submenu = appMenu
        menu.addItem(app)
        let file = NSMenuItem()
        let fileMenu = NSMenu(title: local("文件", "File"))
        let sourceOption = NSMenuItem(title: local("打开原文…", "Open source…"),
                                      action: #selector(openSourceMenuAction), keyEquivalent: "o")
        sourceOption.target = self
        fileMenu.addItem(sourceOption)
        let sessionOption = NSMenuItem(title: local("打开审核会话…", "Open review session…"),
                                       action: #selector(sessionAction), keyEquivalent: "")
        sessionOption.target = self
        fileMenu.addItem(sessionOption)
        let historyOption = NSMenuItem(title: local("之前的工作", "Previous work"),
                                       action: #selector(historyPageAction), keyEquivalent: "")
        historyOption.target = self
        fileMenu.addItem(historyOption)
        fileMenu.addItem(.separator())
        let browserOption = NSMenuItem(title: local("在浏览器中打开", "Open in Browser"),
                                       action: #selector(browserAction), keyEquivalent: "b")
        browserOption.target = self
        fileMenu.addItem(browserOption)
        let saveOption = NSMenuItem(title: local("暂存并返回", "Save and return"),
                                    action: #selector(pauseAction), keyEquivalent: "s")
        saveOption.target = self
        fileMenu.addItem(saveOption)
        file.submenu = fileMenu
        menu.addItem(file)
        let edit = NSMenuItem()
        let editMenu = NSMenu(title: local("编辑", "Edit"))
        for (title, action, key) in [
            (local("撤销", "Undo"), "undo:", "z"),
            (local("重做", "Redo"), "redo:", "Z"),
            (local("剪切", "Cut"), "cut:", "x"),
            (local("复制", "Copy"), "copy:", "c"),
            (local("粘贴", "Paste"), "paste:", "v"),
            (local("全选", "Select All"), "selectAll:", "a")
        ] {
            let item = NSMenuItem(title: title, action: Selector(action), keyEquivalent: key)
            item.target = nil
            editMenu.addItem(item)
        }
        edit.submenu = editMenu
        menu.addItem(edit)
        let api = NSMenuItem()
        let apiMenu = NSMenu(title: "API")
        let configureAPI = NSMenuItem(title: local("配置 API 服务…", "Configure API service…"),
                                      action: #selector(providerAction), keyEquivalent: ",")
        configureAPI.target = self
        apiMenu.addItem(configureAPI)
        api.submenu = apiMenu
        menu.addItem(api)
        let view = NSMenuItem()
        let viewMenu = NSMenu(title: local("视图", "View"))
        for (title, action) in [
            (local("切换浅色／深色", "Toggle light / dark"), #selector(appearanceToggleAction)),
            (local("跟随系统外观", "Use system appearance"), #selector(appearanceSystemAction)),
            (local("切换中文／英文", "Toggle Chinese / English"), #selector(languageAction))
        ] {
            let item = NSMenuItem(title: title, action: action, keyEquivalent: "")
            item.target = self
            viewMenu.addItem(item)
        }
        view.submenu = viewMenu
        menu.addItem(view)
        let windowMenuItem = NSMenuItem()
        let windowMenu = NSMenu(title: local("窗口", "Window"))
        let newWindow = NSMenuItem(title: local("新建并行任务窗口", "New task window"),
                                   action: #selector(newTaskWindowAction), keyEquivalent: "n")
        newWindow.target = self
        windowMenu.addItem(newWindow)
        let minimize = NSMenuItem(title: local("最小化", "Minimize"),
                                  action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        minimize.target = window
        windowMenu.addItem(minimize)
        let zoom = NSMenuItem(title: local("缩放窗口", "Zoom"),
                              action: #selector(NSWindow.performZoom(_:)), keyEquivalent: "")
        zoom.target = window
        windowMenu.addItem(zoom)
        windowMenuItem.submenu = windowMenu
        menu.addItem(windowMenuItem)
        NSApp.windowsMenu = windowMenu
        let help = NSMenuItem()
        let helpMenu = NSMenu(title: local("帮助", "Help"))
        let guide = NSMenuItem(title: local("打开使用指南", "Open user guide"),
                               action: #selector(openGuideAction), keyEquivalent: "?")
        guide.target = self
        helpMenu.addItem(guide)
        help.submenu = helpMenu
        menu.addItem(help)
        NSApp.helpMenu = helpMenu
        NSApp.mainMenu = menu
    }

    @objc private func openSourceMenuAction() {
        if landingPage != .translate { showHome() }
        sourceAction()
    }

    @objc private func openGuideAction() {
        let name = chinese ? "DESKTOP_APP.zh-CN.md" : "DESKTOP_APP.md"
        NSWorkspace.shared.open(desktop.repository.appendingPathComponent("docs").appendingPathComponent(name))
    }

    private func button(_ title: String, _ selector: Selector) -> NSButton {
        let value = NSButton(title: title, target: self, action: selector)
        value.bezelStyle = .rounded
        value.focusRingType = .none
        controls.append(value)
        return value
    }

    private func label(_ title: String, size: CGFloat = 14) -> NSTextField {
        let value = NSTextField(labelWithString: title)
        value.font = NSFont.systemFont(ofSize: size, weight: size >= 20 ? .semibold : .regular)
        return value
    }

    private func row(_ views: NSView...) -> NSStackView {
        let value = NSStackView(views: views)
        value.orientation = .horizontal
        value.alignment = .centerY
        value.spacing = 12
        return value
    }

    private func buildChrome() {
        body = NSView()
        body.translatesAutoresizingMaskIntoConstraints = false
        root.addSubview(body)
        NSLayoutConstraint.activate([
            body.topAnchor.constraint(equalTo: root.safeAreaLayoutGuide.topAnchor),
            body.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            body.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            body.bottomAnchor.constraint(equalTo: root.bottomAnchor)
        ])
    }

    private func showWelcome() {
        landingPage = .welcome
        progressPageActive = false
        body.subviews.forEach { $0.removeFromSuperview() }
        browser = nil
        controls.removeAll()
        let logo = MaterialWebView()
        logo.allowWindowMaterialToShowThrough()
        logo.translatesAutoresizingMaskIntoConstraints = false
        let assets = desktop.repository.appendingPathComponent("review_workbench/static")
        let light = (try? Data(contentsOf: assets.appendingPathComponent("dbabel-logo-light.svg")))?.base64EncodedString() ?? ""
        let dark = (try? Data(contentsOf: assets.appendingPathComponent("dbabel-logo-dark.svg")))?.base64EncodedString() ?? ""
        let html = """
        <!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
        <style>
        html,body{margin:0;background:transparent;height:100%;overflow:hidden}
        svg{display:block;width:100%;height:100%}
        .ink{fill:none;stroke:#12315e;stroke-width:5.2;stroke-linecap:round;
          stroke-linejoin:round;stroke-dasharray:100;stroke-dashoffset:100}
        .written{transform-origin:center;animation:dissolve 5.6s ease-in-out infinite}
        .d1{animation:d1 5.6s cubic-bezier(.68,.04,.16,1) infinite}
        .d2{animation:d2 5.6s cubic-bezier(.68,.04,.16,1) infinite}
        .b1{animation:b1 5.6s cubic-bezier(.68,.04,.16,1) infinite}
        .b2{animation:b2 5.6s cubic-bezier(.68,.04,.16,1) infinite}
        .b3{animation:b3 5.6s cubic-bezier(.68,.04,.16,1) infinite}
        .a{animation:a 5.6s cubic-bezier(.68,.04,.16,1) infinite}
        .lowerb{animation:lowerb 5.6s cubic-bezier(.68,.04,.16,1) infinite}
        .e{animation:e 5.6s cubic-bezier(.68,.04,.16,1) infinite}
        .l{animation:l 5.6s cubic-bezier(.68,.04,.16,1) infinite}
        @keyframes d1{0%,2%{opacity:0;stroke-dashoffset:100}2.1%{opacity:1;stroke-dashoffset:100}12%,100%{opacity:1;stroke-dashoffset:0}}
        @keyframes d2{0%,11%{opacity:0;stroke-dashoffset:100}11.1%{opacity:1;stroke-dashoffset:100}18%,100%{opacity:1;stroke-dashoffset:0}}
        @keyframes b1{0%,17%{opacity:0;stroke-dashoffset:100}17.1%{opacity:1;stroke-dashoffset:100}22%,100%{opacity:1;stroke-dashoffset:0}}
        @keyframes b2{0%,21%{opacity:0;stroke-dashoffset:100}21.1%{opacity:1;stroke-dashoffset:100}27%,100%{opacity:1;stroke-dashoffset:0}}
        @keyframes b3{0%,26%{opacity:0;stroke-dashoffset:100}26.1%{opacity:1;stroke-dashoffset:100}34%,100%{opacity:1;stroke-dashoffset:0}}
        @keyframes a{0%,33%{opacity:0;stroke-dashoffset:100}33.1%{opacity:1;stroke-dashoffset:100}45%,100%{opacity:1;stroke-dashoffset:0}}
        @keyframes lowerb{0%,44%{opacity:0;stroke-dashoffset:100}44.1%{opacity:1;stroke-dashoffset:100}59%,100%{opacity:1;stroke-dashoffset:0}}
        @keyframes e{0%,58%{opacity:0;stroke-dashoffset:100}58.1%{opacity:1;stroke-dashoffset:100}68%,100%{opacity:1;stroke-dashoffset:0}}
        @keyframes l{0%,67%{opacity:0;stroke-dashoffset:100}67.1%{opacity:1;stroke-dashoffset:100}78%,100%{opacity:1;stroke-dashoffset:0}}
        @keyframes dissolve{0%,85%{opacity:1;filter:blur(0);transform:translateY(0) scale(1)}
          96%{opacity:.15;filter:blur(11px);transform:translateY(-8px) scale(1.045)}
          100%{opacity:0;filter:blur(15px);transform:translateY(-12px) scale(1.06)}}
        .static-logo{display:none}
        @media(prefers-color-scheme:dark){.ink{stroke:#f4f4fa}}
        @media(prefers-reduced-motion:reduce){.written{display:none}.static-logo.light{display:block}}
        @media(prefers-reduced-motion:reduce) and (prefers-color-scheme:dark){
          .static-logo.light{display:none}.static-logo.dark{display:block}}
        </style></head><body>
        <svg viewBox="0 0 236 91" aria-label="DBabel">
          <g class="written">
            <path class="ink d1" pathLength="100" d="M4 36 C17 24 30 19 44 22 C57 24 63 32 59 43 C54 58 31 75 6 86"/>
            <path class="ink d2" pathLength="100" d="M28 20 C23 43 14 67 10 85"/>
            <path class="ink b1" pathLength="100" d="M71 23 C66 39 63 60 59 75"/>
            <path class="ink b2" pathLength="100" d="M73 48 C79 34 90 20 98 19 C109 27 91 43 74 49"/>
            <path class="ink b3" pathLength="100" d="M74 49 C89 45 99 47 99 56 C95 68 72 79 53 82"/>
            <path class="ink a" pathLength="100" d="M124 45 C114 42 104 50 102 62 C103 70 114 61 122 48 C116 58 119 67 127 65"/>
            <path class="ink lowerb" pathLength="100" d="M156 13 C148 31 138 55 136 67 C147 64 160 51 156 43 C151 37 139 50 135 65"/>
            <path class="ink e" pathLength="100" d="M164 59 C176 61 189 49 180 44 C172 40 163 51 164 61 C165 70 178 64 190 55"/>
            <path class="ink l" pathLength="100" d="M215 13 C205 25 197 45 193 59 C188 77 208 63 231 45"/>
          </g>
          <image class="static-logo light" width="236" height="91" href="data:image/svg+xml;base64,\(light)"/>
          <image class="static-logo dark" width="236" height="91" href="data:image/svg+xml;base64,\(dark)"/>
        </svg></body></html>
        """
        logo.loadHTMLString(html, baseURL: nil)
        let heading = label(local("欢迎使用 DBabel", "Welcome to DBabel"), size: 16)
        heading.textColor = .secondaryLabelColor
        let translate = button(local("AI 翻译全流程", "AI translation workflow"), #selector(translatePageAction))
        translate.bezelStyle = .rounded
        translate.controlSize = .large
        translate.font = .systemFont(ofSize: 16, weight: .medium)
        translate.keyEquivalent = "\r"
        let review = button(local("本地双语对照审核", "Local bilingual review"), #selector(localReviewPageAction))
        review.bezelStyle = .rounded
        review.controlSize = .large
        review.font = .systemFont(ofSize: 16, weight: .medium)
        let options = row(translate, review)
        options.spacing = 20
        let history = button(local("继续之前的工作", "Continue previous work"),
                             #selector(historyPageAction))
        history.controlSize = .large
        let stack = NSStackView(views: [logo, heading, options, history])
        stack.orientation = .vertical
        stack.alignment = .centerX
        stack.spacing = 20
        stack.translatesAutoresizingMaskIntoConstraints = false
        body.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.centerXAnchor.constraint(equalTo: body.centerXAnchor),
            stack.centerYAnchor.constraint(equalTo: body.centerYAnchor, constant: -36),
            stack.widthAnchor.constraint(lessThanOrEqualTo: body.widthAnchor, multiplier: 0.8),
            logo.widthAnchor.constraint(greaterThanOrEqualToConstant: 505),
            logo.widthAnchor.constraint(lessThanOrEqualToConstant: 760),
            {
                let adaptiveWidth = logo.widthAnchor.constraint(equalTo: body.widthAnchor, multiplier: 0.34)
                adaptiveWidth.priority = .defaultHigh
                return adaptiveWidth
            }(),
            logo.heightAnchor.constraint(equalTo: logo.widthAnchor, multiplier: 91.0 / 236.0),
            translate.widthAnchor.constraint(greaterThanOrEqualToConstant: 226),
            review.widthAnchor.constraint(greaterThanOrEqualToConstant: 226),
            translate.heightAnchor.constraint(equalToConstant: 52),
            review.heightAnchor.constraint(equalToConstant: 52)
        ])
        stack.setCustomSpacing(34, after: heading)
        stack.setCustomSpacing(28, after: options)
    }

    @objc private func translatePageAction() { showHome() }
    @objc private func localReviewPageAction() { showLocalReview() }
    @objc private func welcomeAction() { showWelcome() }
    @objc private func historyPageAction() { showHistory() }

    private func showHistory() {
        landingPage = .history
        progressPageActive = false
        body.subviews.forEach { $0.removeFromSuperview() }
        browser = nil
        controls.removeAll()

        let sidebar = NSView()
        sidebar.translatesAutoresizingMaskIntoConstraints = false
        body.addSubview(sidebar)
        let navigationButtons = [
            button(local("最近任务", "Recent work"), #selector(historyPageAction)),
            button(local("AI 翻译", "AI translation"), #selector(translatePageAction)),
            button(local("本地双语审核", "Local review"), #selector(localReviewPageAction)),
            button(local("返回欢迎页", "Welcome"), #selector(welcomeAction))
        ]
        for item in navigationButtons {
            item.controlSize = .large
            item.font = .systemFont(ofSize: 16, weight: .medium)
            item.alignment = .left
            item.widthAnchor.constraint(equalToConstant: 188).isActive = true
            item.heightAnchor.constraint(equalToConstant: 42).isActive = true
        }
        let navigationTitle = label("DBabel", size: 29)
        let navigation = NSStackView(views: [navigationTitle] + navigationButtons)
        navigation.orientation = .vertical
        navigation.alignment = .leading
        navigation.spacing = 14
        navigation.setCustomSpacing(32, after: navigationTitle)
        navigation.translatesAutoresizingMaskIntoConstraints = false
        sidebar.addSubview(navigation)
        NSLayoutConstraint.activate([
            sidebar.topAnchor.constraint(equalTo: body.topAnchor),
            sidebar.bottomAnchor.constraint(equalTo: body.bottomAnchor),
            sidebar.leadingAnchor.constraint(equalTo: body.leadingAnchor),
            sidebar.widthAnchor.constraint(equalToConstant: 250),
            navigation.topAnchor.constraint(equalTo: sidebar.topAnchor, constant: 42),
            navigation.leadingAnchor.constraint(equalTo: sidebar.leadingAnchor, constant: 25)
        ])

        let sessions = desktop.savedSessions()
        let heading = label(local("之前的工作", "Previous work"), size: 31)
        let subheading = label(local("选择一个任务，继续上次的审核和 AI 对话。",
                                     "Open a saved task to continue its review and AI conversation."))
        subheading.textColor = .secondaryLabelColor
        let grid = ResponsiveSessionGrid()
        grid.translatesAutoresizingMaskIntoConstraints = false
        if sessions.isEmpty {
            grid.install([])
        }
        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        formatter.timeStyle = .short
        var cards: [NSView] = []
        for saved in sessions.prefix(20) {
                let card = NSBox()
                card.boxType = .custom
                card.cornerRadius = 18
                card.borderWidth = 1
                card.borderColor = NSColor.separatorColor.withAlphaComponent(0.28)
                card.fillColor = .clear
                let icon = NSImageView(image: NSWorkspace.shared.icon(for: .folder))
                icon.imageScaling = .scaleProportionallyUpOrDown
                let title = label(saved.title, size: 16)
                title.lineBreakMode = .byTruncatingMiddle
                title.maximumNumberOfLines = 2
                let date = label(formatter.string(from: saved.updated), size: 12)
                date.textColor = .secondaryLabelColor
                let open = button(local("继续审核", "Continue review"), #selector(openSavedSessionAction(_:)))
                open.identifier = NSUserInterfaceItemIdentifier(saved.bundle.path)
                let content = NSStackView(views: [icon, title, date, open])
                content.orientation = .vertical
                content.alignment = .leading
                content.spacing = 13
                content.translatesAutoresizingMaskIntoConstraints = false
                card.contentView?.addSubview(content)
                NSLayoutConstraint.activate([
                    icon.widthAnchor.constraint(equalToConstant: 142),
                    icon.heightAnchor.constraint(equalToConstant: 112),
                    content.topAnchor.constraint(equalTo: card.contentView!.topAnchor, constant: 18),
                    content.leadingAnchor.constraint(equalTo: card.contentView!.leadingAnchor, constant: 17),
                    content.trailingAnchor.constraint(lessThanOrEqualTo: card.contentView!.trailingAnchor, constant: -17),
                    title.widthAnchor.constraint(lessThanOrEqualToConstant: 265)
                ])
                cards.append(card)
        }
        if !cards.isEmpty { grid.install(cards) }
        let openOther = button(local("打开其他 .dbreview 会话…", "Open another .dbreview session…"),
                               #selector(sessionAction))
        let content = NSStackView(views: [heading, subheading, grid, openOther])
        content.orientation = .vertical
        content.alignment = .leading
        content.spacing = 22
        content.translatesAutoresizingMaskIntoConstraints = false
        let scroll = NSScrollView()
        scroll.drawsBackground = false
        scroll.contentView.drawsBackground = false
        scroll.hasVerticalScroller = true
        scroll.translatesAutoresizingMaskIntoConstraints = false
        let document = FlippedView()
        document.translatesAutoresizingMaskIntoConstraints = false
        document.addSubview(content)
        scroll.documentView = document
        body.addSubview(scroll)
        NSLayoutConstraint.activate([
            scroll.topAnchor.constraint(equalTo: body.topAnchor),
            scroll.bottomAnchor.constraint(equalTo: body.bottomAnchor),
            scroll.leadingAnchor.constraint(equalTo: sidebar.trailingAnchor),
            scroll.trailingAnchor.constraint(equalTo: body.trailingAnchor),
            document.widthAnchor.constraint(equalTo: scroll.contentView.widthAnchor),
            content.topAnchor.constraint(equalTo: document.topAnchor, constant: 44),
            content.leadingAnchor.constraint(equalTo: document.leadingAnchor, constant: 38),
            content.trailingAnchor.constraint(equalTo: document.trailingAnchor, constant: -38),
            grid.widthAnchor.constraint(equalTo: content.widthAnchor),
            content.bottomAnchor.constraint(equalTo: document.bottomAnchor, constant: -38)
        ])
    }

    private func showLocalReview() {
        landingPage = .localReview
        progressPageActive = false
        body.subviews.forEach { $0.removeFromSuperview() }
        browser = nil
        controls.removeAll()
        sourceName.stringValue = source?.lastPathComponent ?? local("未选择文件", "No file selected")
        targetName.stringValue = existingTarget?.lastPathComponent ?? local("未选择译文", "No target selected")
        alignmentConfirmed.title = local("我已核对原文和现有译文的单元顺序一致",
                                         "I checked that source and target segments align in order")
        alignmentConfirmed.isHidden = existingTarget == nil
        let title = label(local("本地双语对照审核", "Local bilingual review"), size: 30)
        let description = NSTextField(wrappingLabelWithString: local(
            "导入原文和可选的现有译文，建立本地审核会话。此入口不会调用 API。",
            "Import a source and optional existing translation to create a local review session. This path does not call an API."))
        description.textColor = .secondaryLabelColor
        let demoAndHistory = row(button(local("查看演示", "View demo"), #selector(demoAction)),
                                 button(local("之前的工作", "Previous work"), #selector(historyPageAction)))
        demoAndHistory.spacing = 18
        let stack = NSStackView(views: [
            title, description,
            row(button(local("选择原文", "Choose source"), #selector(sourceAction)),sourceName),
            row(label(local("原文语言", "Source language")),from,label("→"),label(local("目标语言", "Target language")),to),
            row(button(local("选择现有译文", "Choose existing translation"), #selector(targetAction)),targetName,
                button(local("清除", "Clear"), #selector(clearTargetAction))),
            alignmentConfirmed,
            button(local("打开审核工作台", "Open review Workbench"), #selector(uploadAction)),
            demoAndHistory,
            status
        ])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 24
        stack.setCustomSpacing(32, after: description)
        for control in controls {
            control.controlSize = .large
            control.font = .systemFont(ofSize: 15, weight: .medium)
            control.heightAnchor.constraint(greaterThanOrEqualToConstant: 40).isActive = true
        }
        stack.translatesAutoresizingMaskIntoConstraints = false
        body.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.topAnchor.constraint(equalTo: body.topAnchor, constant: 52),
            stack.leadingAnchor.constraint(equalTo: body.leadingAnchor, constant: 56),
            stack.trailingAnchor.constraint(lessThanOrEqualTo: body.trailingAnchor, constant: -40),
            description.widthAnchor.constraint(lessThanOrEqualToConstant: 760)
        ])
    }

    @objc private func resumeLatestSessionAction() {
        let preferred = UserDefaults.standard.string(forKey: "DBabelLastReviewBundle.v1")
        let bundle = preferred.flatMap { path -> URL? in
            let candidate = URL(fileURLWithPath: path)
            return FileManager.default.fileExists(atPath: candidate.appendingPathComponent("session.json").path)
                ? candidate : nil
        } ?? desktop.savedSessions().first?.bundle
        guard let bundle else {
            status.stringValue = local("尚无可恢复的审核会话。", "No review session is available to resume.")
            return
        }
        desktop.openSession(bundle)
    }

    private func showHome() {
        landingPage = .translate
        progressPageActive = false
        body.subviews.forEach { $0.removeFromSuperview() }
        browser = nil
        controls.removeAll()
        sourceName.stringValue = source?.lastPathComponent ?? local("未选择文件", "No file selected")
        targetName.stringValue = existingTarget?.lastPathComponent ?? local("未选择译文", "No target selected")
        for name in [sourceName, targetName] { name.lineBreakMode = .byTruncatingMiddle }
        alignmentConfirmed.title = local("我已核对原文和现有译文的单元顺序一致",
                                         "I checked that source and existing target segments align in order")
        alignmentConfirmed.isHidden = existingTarget == nil
        providerName.stringValue = providerSettings.map { "\($0.model) · \($0.baseURL)" }
            ?? local("尚未配置 API 服务", "API service not configured")
        pendingResume = matchingResumeRun()
        if !homeFieldConstraintsSet {
            [from, to, role, sourceName, targetName].forEach {
                $0.translatesAutoresizingMaskIntoConstraints = false
            }
            NSLayoutConstraint.activate([
                from.widthAnchor.constraint(equalToConstant: 235),
                to.widthAnchor.constraint(equalToConstant: 235),
                role.widthAnchor.constraint(equalToConstant: 200),
                sourceName.widthAnchor.constraint(lessThanOrEqualToConstant: 430),
                targetName.widthAnchor.constraint(lessThanOrEqualToConstant: 430)
            ])
            homeFieldConstraintsSet = true
        }
        let introduction = NSTextField(wrappingLabelWithString: local(
            "选择原文并配置 API 服务。完成预检、翻译和 QA 后，在本窗口审核并导出。",
            "Choose a source and configure an API service. Review and export here after translation and QA."))
        introduction.textColor = .secondaryLabelColor
        let uploadHelp = NSTextField(wrappingLabelWithString: local(
            "也可用上方选定的原文建立本地审核会话；已有译文可在此选择。此入口不调用 API，也不会自动生成译文。",
            "Create a local review session from the source selected above; optionally choose an existing translation. This path does not call an API or generate a translation."))
        uploadHelp.textColor = .secondaryLabelColor
        let greeting = label("HELLO,THERE!", size: 44)
        greeting.font = NSFont.systemFont(ofSize: 44, weight: .medium)
        greeting.textColor = .labelColor
        status.lineBreakMode = .byWordWrapping
        status.maximumNumberOfLines = 0
        let resumeRow = row(button(local("继续上次运行", "Resume previous run"), #selector(resumeAction)),
                            label(pendingResume?.source.lastPathComponent ?? ""))
        resumeRow.isHidden = pendingResume == nil
        let titleRow = row(label(local("翻译文档", "Translate a document"), size: 30),
                           button(local("打开演示", "Open demo"), #selector(demoAction)))
        titleRow.spacing = 20
        let uploadHeading = label(local("上传文档并建立审核会话", "Upload documents for review"), size: 22)
        let sessionHeading = label(local("已有会话", "Existing session"), size: 22)
        let stack = NSStackView(views: [
            greeting,
            titleRow,
            introduction,
            row(button(local("选择原文", "Choose source"), #selector(sourceAction)), sourceName),
            row(label(local("原文语言", "Source language")), from, label("→"),
                label(local("目标语言", "Target language")), to),
            row(label(local("文本角色", "Text role")), role),
            row(button(local("配置 API 服务", "Configure API service"), #selector(providerAction)), providerName),
            button(local("翻译并打开审核工作台", "Translate and open Workbench"), #selector(translateAction)),
            resumeRow,
            uploadHeading,
            uploadHelp,
            row(button(local("选择现有译文（可选）", "Choose existing target (optional)"), #selector(targetAction)),
                targetName, button(local("清除", "Clear"), #selector(clearTargetAction))),
            alignmentConfirmed,
            button(local("上传文档并打开工作台", "Upload documents and open Workbench"), #selector(uploadAction)),
            sessionHeading,
            button(local("打开 .dbreview 会话", "Open .dbreview session"), #selector(sessionAction)),
            status
        ])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 18
        stack.setCustomSpacing(30, after: greeting)
        stack.setCustomSpacing(24, after: introduction)
        stack.setCustomSpacing(30, after: resumeRow)
        stack.setCustomSpacing(24, after: uploadHelp)
        stack.setCustomSpacing(30, after: sessionHeading)
        stack.addArrangedSubview(button(local("查看之前的工作", "Browse previous work"),
                                        #selector(historyPageAction)))
        stack.addArrangedSubview(button(local("新建并行任务窗口", "New parallel task window"),
                                       #selector(newTaskWindowAction)))
        for control in controls {
            control.controlSize = .large
            control.font = .systemFont(ofSize: 15, weight: .medium)
            control.heightAnchor.constraint(greaterThanOrEqualToConstant: 36).isActive = true
        }
        stack.translatesAutoresizingMaskIntoConstraints = false
        let scroll = NSScrollView()
        scroll.drawsBackground = false
        scroll.contentView.drawsBackground = false
        scroll.hasVerticalScroller = true
        scroll.autohidesScrollers = true
        scroll.translatesAutoresizingMaskIntoConstraints = false
        let content = FlippedView()
        content.translatesAutoresizingMaskIntoConstraints = false
        content.addSubview(stack)
        scroll.documentView = content
        body.addSubview(scroll)
        NSLayoutConstraint.activate([
            scroll.topAnchor.constraint(equalTo: body.topAnchor),
            scroll.leadingAnchor.constraint(equalTo: body.leadingAnchor),
            scroll.trailingAnchor.constraint(equalTo: body.trailingAnchor),
            scroll.bottomAnchor.constraint(equalTo: body.bottomAnchor),
            content.widthAnchor.constraint(equalTo: scroll.contentView.widthAnchor),
            stack.topAnchor.constraint(equalTo: content.topAnchor, constant: 44),
            stack.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 48),
            stack.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -40),
            stack.bottomAnchor.constraint(equalTo: content.bottomAnchor, constant: -32)
        ])
    }

    private let progressStageIDs = ["FORMAT_PROBE", "INGEST", "TRANSLATION",
                                    "POST_TRANSLATION_QA", "ADJUDICATION",
                                    "REVIEW_SESSION_BINDING", "DELIVERY_VALIDATION"]

    private func progressStageName(_ id: String) -> String {
        switch id {
        case "FORMAT_PROBE": return local("文档预检", "Document preflight")
        case "INGEST": return local("提取审核单元", "Extract review units")
        case "TRANSLATION": return local("生成翻译建议", "Generate translation proposals")
        case "POST_TRANSLATION_QA": return local("确定性 QA", "Deterministic QA")
        case "ADJUDICATION": return local("语义复核", "Semantic review")
        case "REVIEW_SESSION_BINDING": return local("建立审核会话", "Create review session")
        case "DELIVERY_VALIDATION": return local("验证并打开工作台", "Validate and open Workbench")
        default: return id
        }
    }

    private func showProgress() {
        landingPage = .progress
        progressPageActive = true
        progressLastEvent = nil
        body.subviews.forEach { $0.removeFromSuperview() }
        browser = nil
        progressHeading.font = .systemFont(ofSize: 34, weight: .semibold)
        progressHeading.stringValue = local("正在准备翻译", "Preparing translation")
        progressDetail.stringValue = local("正在检查文档格式…", "Checking document format…")
        progressDetail.textColor = .secondaryLabelColor
        progressUnit.stringValue = local("等待提取审核单元", "Waiting for review units")
        progressUnit.font = .systemFont(ofSize: 22, weight: .semibold)
        progressSource.stringValue = ""
        progressSource.textColor = .secondaryLabelColor
        progressSource.maximumNumberOfLines = 3
        progressBar.isIndeterminate = true
        progressBar.style = .bar
        progressBar.minValue = 0
        progressBar.maxValue = 1
        progressBar.startAnimation(nil)
        progressSteps = progressStageIDs.map { id in
            let field = label("○  " + progressStageName(id), size: 17)
            field.textColor = .secondaryLabelColor
            return field
        }
        progressDocument.stringValue = source?.lastPathComponent ?? ""
        progressDocument.font = .systemFont(ofSize: 22, weight: .medium)
        progressDocument.lineBreakMode = .byTruncatingMiddle
        progressDocument.textColor = .labelColor
        progressDocument.wantsLayer = true
        if !NSWorkspace.shared.accessibilityDisplayShouldReduceMotion {
            let breathe = CABasicAnimation(keyPath: "opacity")
            breathe.fromValue = 1.0
            breathe.toValue = 0.72
            breathe.duration = 1.5
            breathe.autoreverses = true
            breathe.repeatCount = .infinity
            progressDocument.layer?.add(breathe, forKey: "documentBreathe")
        }
        let stepsHeading = label(local("处理步骤", "Processing steps"), size: 22)
        let currentHeading = label(local("当前处理", "Current work"), size: 22)
        let stack = NSStackView(views: [
            progressHeading, progressDocument, progressDetail, progressBar,
            stepsHeading
        ] + progressSteps + [
            currentHeading,
            progressUnit, progressSource
        ])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 18
        stack.setCustomSpacing(28, after: progressBar)
        stack.setCustomSpacing(22, after: stepsHeading)
        if let lastStep = progressSteps.last { stack.setCustomSpacing(32, after: lastStep) }
        stack.translatesAutoresizingMaskIntoConstraints = false
        body.addSubview(stack)
        let preferredWidth = stack.widthAnchor.constraint(equalTo: body.widthAnchor, constant: -104)
        preferredWidth.priority = .defaultHigh
        NSLayoutConstraint.activate([
            preferredWidth,
            stack.topAnchor.constraint(equalTo: body.topAnchor, constant: 44),
            stack.leadingAnchor.constraint(equalTo: body.leadingAnchor, constant: 52),
            stack.trailingAnchor.constraint(lessThanOrEqualTo: body.trailingAnchor, constant: -52),
            stack.widthAnchor.constraint(lessThanOrEqualToConstant: 900),
            progressBar.widthAnchor.constraint(equalTo: stack.widthAnchor),
            progressDetail.widthAnchor.constraint(equalTo: stack.widthAnchor),
            progressSource.widthAnchor.constraint(equalTo: stack.widthAnchor)
        ])
    }

    private func updateProgress(_ event: [String: Any]) {
        guard progressPageActive,
              let stage = event["stage"] as? String,
              let index = progressStageIDs.firstIndex(of: stage) else { return }
        progressLastEvent = event
        let state = event["state"] as? String ?? ""
        for (position, field) in progressSteps.enumerated() {
            let marker = position < index || (position == index && state == "COMPLETED")
                ? "✓" : position == index ? "●" : "○"
            field.stringValue = marker + "  " + progressStageName(progressStageIDs[position])
            field.textColor = position == index ? .labelColor : .secondaryLabelColor
            field.wantsLayer = true
            if position == index && state != "COMPLETED"
                && !NSWorkspace.shared.accessibilityDisplayShouldReduceMotion {
                if field.layer?.animation(forKey: "progressPulse") == nil {
                    let pulse = CABasicAnimation(keyPath: "opacity")
                    pulse.fromValue = 1.0
                    pulse.toValue = 0.56
                    pulse.duration = 0.9
                    pulse.autoreverses = true
                    pulse.repeatCount = .infinity
                    field.layer?.add(pulse, forKey: "progressPulse")
                }
            } else {
                field.layer?.removeAnimation(forKey: "progressPulse")
            }
        }
        progressHeading.stringValue = progressStageName(stage)
        let completed = event["completed_units"] as? Int ?? 0
        let total = event["total_units"] as? Int ?? 0
        if total > 0 {
            progressBar.stopAnimation(nil)
            progressBar.isIndeterminate = false
            progressBar.maxValue = Double(total)
            progressBar.doubleValue = Double(completed)
            progressDetail.stringValue = local("已处理 \(completed) / \(total) 个审核单元",
                                                "Processed \(completed) / \(total) review units")
        } else {
            progressBar.isIndeterminate = true
            progressBar.startAnimation(nil)
            progressDetail.stringValue = local("正在进行" + progressStageName(stage) + "…",
                                                "Running " + progressStageName(stage) + "…")
        }
        if state == "BATCH_SPLIT" {
            let size = event["next_batch_units"] as? Int ?? 1
            progressDetail.stringValue = local("响应中断，已保留完成进度；改用每批 \(size) 个单元继续。",
                                                "Response interrupted; progress saved. Continuing with \(size) units per batch.")
        } else if state == "CONTRACT_RETRY" {
            progressDetail.stringValue = local("正在重新校验返回格式，已完成内容保持保存。",
                                                "Retrying response validation; completed work remains saved.")
        } else if state == "SPLITTING_BATCH" {
            progressDetail.stringValue = local("技术标记需要复核，正在拆小批次重试…",
                                                "A technical literal needs review; retrying smaller batches…")
        } else if state == "RETRYING_LITERAL" {
            let attempt = event["retry"] as? Int ?? 1
            progressDetail.stringValue = local("技术标记次数不符，正在重试（\(attempt)/2）…",
                                                "Literal count mismatch; retrying (\(attempt)/2)…")
        } else if state == "REVIEW_REQUIRED" {
            progressDetail.stringValue = local("该单元保留为待人工修正，继续处理后续内容。",
                                                "This unit needs human correction; continuing with the document.")
        }
        if let unitID = event["unit_id"] as? String {
            let location = event["location"] as? String ?? ""
            progressUnit.stringValue = local("单元 \(unitID)  ·  \(location)",
                                             "Unit \(unitID)  ·  \(location)")
        }
        if let preview = event["source_preview"] as? String, !preview.isEmpty {
            progressSource.stringValue = preview
        }
    }

    private func showProgressFailure(_ message: String) {
        guard progressPageActive else { return }
        progressBar.stopAnimation(nil)
        progressDocument.layer?.removeAnimation(forKey: "documentBreathe")
        progressHeading.stringValue = local("翻译未完成", "Translation did not complete")
        progressDetail.stringValue = message
        progressDetail.textColor = .systemRed
        progressUnit.stringValue = local("请查看上方原因，调整后重试。", "Review the reason above, then retry.")
        progressSource.stringValue = ""
        let back = button(local("返回首页", "Back to home"), #selector(homeAction))
        back.translatesAutoresizingMaskIntoConstraints = false
        body.addSubview(back)
        let resume = button(local("继续本次运行", "Resume this run"), #selector(resumeAction))
        resume.translatesAutoresizingMaskIntoConstraints = false
        if let candidate = matchingResumeRun(), candidate.source == source {
            pendingResume = candidate
            body.addSubview(resume)
            NSLayoutConstraint.activate([
                resume.leadingAnchor.constraint(equalTo: back.trailingAnchor, constant: 12),
                resume.centerYAnchor.constraint(equalTo: back.centerYAnchor)
            ])
        }
        NSLayoutConstraint.activate([
            back.leadingAnchor.constraint(equalTo: body.leadingAnchor, constant: 52),
            back.bottomAnchor.constraint(equalTo: body.bottomAnchor, constant: -40)
        ])
    }

    private func showWorkbench(_ url: URL) {
        landingPage = .workbench
        if let bundle = desktop.lastBundle {
            UserDefaults.standard.set(bundle.path, forKey: "DBabelLastReviewBundle.v1")
        }
        progressPageActive = false
        body.subviews.forEach { $0.removeFromSuperview() }
        let view = MaterialWebView()
        view.allowWindowMaterialToShowThrough()
        view.navigationDelegate = self
        view.uiDelegate = self
        view.translatesAutoresizingMaskIntoConstraints = false
        body.addSubview(view)
        NSLayoutConstraint.activate([
            view.topAnchor.constraint(equalTo: body.topAnchor),
            view.leadingAnchor.constraint(equalTo: body.leadingAnchor),
            view.trailingAnchor.constraint(equalTo: body.trailingAnchor),
            view.bottomAnchor.constraint(equalTo: body.bottomAnchor)
        ])
        browser = view
        var components = URLComponents(url: url, resolvingAgainstBaseURL: false)!
        let accent = NSColor.controlAccentColor.usingColorSpace(.deviceRGB) ?? .systemBlue
        let accentHex = String(format: "#%02X%02X%02X",
                               Int(accent.redComponent * 255),
                               Int(accent.greenComponent * 255),
                               Int(accent.blueComponent * 255))
        components.queryItems = [URLQueryItem(name: "desktop", value: "macos"),
                                 URLQueryItem(name: "accent", value: accentHex),
                                 URLQueryItem(name: "appearance", value: appearance.rawValue)]
        let desktopURL = components.url!
        currentURL = desktopURL
        view.load(URLRequest(url: desktopURL))
    }

    private func clearToolbarFocus() {
        DispatchQueue.main.async { [weak self] in
            guard let self, self.providerSheet == nil else { return }
            self.window.makeFirstResponder(nil)
        }
    }

    @objc private func homeAction() {
        clearToolbarFocus()
        if desktop.busy && progressPageActive { return }
        leaveWorkbench { [weak self] saved in if saved { self?.showWelcome() } }
    }
    private func showUnsavedAlert() {
        let alert = NSAlert()
        alert.messageText = local("进度尚未保存", "Progress could not be saved")
        alert.informativeText = local("请检查本地会话文件是否可写，然后重试。当前工作台会保持打开。",
                                      "Check that the local session is writable and try again. The Workbench remains open.")
        alert.runModal()
    }
    @objc private func pauseAction() {
        clearToolbarFocus()
        leaveWorkbench { [weak self] saved in if saved { self?.showWelcome() } }
    }
    private func leaveWorkbench(completion: @escaping (Bool) -> Void) {
        guard landingPage == .workbench, let browser else { completion(true); return }
        browser.evaluateJavaScript("window.workbenchNeedsSave?.()") { [weak self] result, error in
            guard let self else { completion(false); return }
            if error != nil { self.showUnsavedAlert(); completion(false); return }
            if result as? Bool == true {
                let alert = NSAlert()
                alert.messageText = self.local("离开工作台？", "Leave the Workbench?")
                let path = self.desktop.lastBundle?.path ?? ""
                alert.informativeText = self.local(
                    "当前译文或审核备注有新修改。默认保存到本地会话：\n\(path)",
                    "The current translation or note has new edits. Save to the local session by default:\n\(path)")
                alert.addButton(withTitle: self.local("保存并离开", "Save and Leave"))
                alert.addButton(withTitle: self.local("不保存本次修改", "Discard New Edits"))
                alert.addButton(withTitle: self.local("取消", "Cancel"))
                switch alert.runModal() {
                case .alertFirstButtonReturn: self.finishLeavingWorkbench("window.flushWorkbenchUiState?.()", completion: completion)
                case .alertSecondButtonReturn: self.finishLeavingWorkbench("window.discardWorkbenchCurrentDraft?.()", completion: completion)
                default: completion(false)
                }
            } else {
                self.finishLeavingWorkbench("window.flushWorkbenchUiState?.()", completion: completion)
            }
        }
    }
    private func finishLeavingWorkbench(_ script: String, completion: @escaping (Bool) -> Void) {
        guard let browser else { completion(false); return }
        browser.callAsyncJavaScript("return await \(script);", arguments: [:],
                                    in: nil, in: .page) { [weak self] result in
            guard let self else { completion(false); return }
            switch result {
            case .success(let value) where value as? Bool == true: completion(true)
            default: self.showUnsavedAlert(); completion(false)
            }
        }
    }
    @objc private func browserAction() {
        if let url = currentURL { NSWorkspace.shared.open(url) }
    }
    private func setAppearance(_ value: DesktopAppearance) {
        appearance = value
        switch value {
        case .system: window.appearance = nil
        case .light: window.appearance = NSAppearance(named: .aqua)
        case .dark: window.appearance = NSAppearance(named: .darkAqua)
        }
        browser?.evaluateJavaScript("window.dbabelSetDesktopTheme?.('\(value.rawValue)')")
    }
    @objc private func appearanceToggleAction() {
        clearToolbarFocus()
        let effectiveDark = appearance == .dark ||
            (appearance == .system && window.effectiveAppearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua)
        setAppearance(effectiveDark ? .light : .dark)
    }
    @objc private func appearanceSystemAction() { setAppearance(.system) }
    @objc private func appearanceLightAction() { setAppearance(.light) }
    @objc private func appearanceDarkAction() { setAppearance(.dark) }

    @objc private func languageAction() {
        clearToolbarFocus()
        guard let browser = browser else {
            chinese.toggle()
            refreshNativeLanguage()
            if progressPageActive {
                let last = progressLastEvent
                showProgress()
                if let last = last { updateProgress(last) }
            } else {
                switch landingPage {
                case .welcome: showWelcome()
                case .localReview: showLocalReview()
                case .history: showHistory()
                default: showHome()
                }
            }
            return
        }
        let script = """
        (() => { const control = document.getElementById('languageSelect');
          if (!control) return '';
          control.value = control.value === 'zh-CN' ? 'en' : 'zh-CN';
          control.dispatchEvent(new Event('change', {bubbles:true}));
          return control.value; })()
        """
        browser.evaluateJavaScript(script) { [weak self] result, _ in
            if let language = result as? String, !language.isEmpty {
                self?.chinese = language == "zh-CN"
                self?.refreshNativeLanguage()
            }
        }
    }
    private func refreshNativeLanguage() {
        buildMenus()
        window.toolbar?.items.forEach { item in
            switch item.itemIdentifier {
            case homeItem: item.label = local("首页", "Home")
            case providerItem: item.label = local("API 服务", "API Service")
            case appearanceItem: item.label = local("外观", "Appearance")
            case languageItem: item.label = local("语言", "Language")
            case pauseItem: item.label = local("暂存并返回", "Save and return")
            default: break
            }
        }
    }
    @objc private func sourceAction() {
        if let selected = chooseFile(extensions: ["docx", "txt", "md", "xlsx"]) {
            source = selected
            sourceName.stringValue = selected.lastPathComponent
        }
    }
    @objc private func targetAction() {
        if let selected = chooseFile(extensions: ["docx", "txt", "md", "xlsx"]) {
            existingTarget = selected
            targetName.stringValue = selected.lastPathComponent
            alignmentConfirmed.isHidden = false
            alignmentConfirmed.state = .off
        }
    }
    @objc private func clearTargetAction() {
        existingTarget = nil
        targetName.stringValue = local("未选择译文", "No target selected")
        alignmentConfirmed.state = .off
        alignmentConfirmed.isHidden = true
    }
    @objc private func uploadAction() {
        guard let source = source else {
            status.stringValue = local("请先选择原文。", "Choose a source document first.")
            return
        }
        guard languagesAreValid() else { return }
        if existingTarget?.standardizedFileURL == source.standardizedFileURL {
            status.stringValue = local("现有译文不能与原文是同一个文件。",
                                       "Choose a target file different from the source.")
            return
        }
        if existingTarget != nil && alignmentConfirmed.state != .on {
            status.stringValue = local("请先核对原文与现有译文的单元顺序，再勾选确认。",
                                       "Check source/target segment order and confirm alignment first.")
            return
        }
        desktop.createReviewSession(source: source, target: existingTarget,
                                    from: languageCode(from), to: languageCode(to),
                                    alignmentConfirmed: alignmentConfirmed.state == .on)
    }
    @objc private func providerAction() { showProviderSheet() }

    private func showProviderSheet() {
        if providerSheet != nil { return }
        apiBaseURL.stringValue = providerSettings?.baseURL ?? ""
        apiModel.stringValue = providerSettings?.model ?? ""
        apiProxy.stringValue = providerSettings?.proxyURL ?? ""
        apiProxyMode.removeAllItems()
        apiProxyMode.addItems(withTitles: [local("跟随系统", "Use system"),
                                          local("不使用代理", "No proxy"),
                                          local("自定义代理", "Custom proxy")])
        let savedProxyMode = providerSettings?.effectiveProxyMode ?? "system"
        apiProxyMode.selectItem(at: ["system", "none", "custom"].firstIndex(of: savedProxyMode) ?? 0)
        apiProxyMode.target = self
        apiProxyMode.action = #selector(proxyModeAction)
        apiProxy.isEnabled = apiProxyMode.indexOfSelectedItem == 2
        apiTrustedHTTP.title = local("允许连接可信内部 HTTP 服务", "Allow trusted internal HTTP service")
        apiTrustedHTTP.state = providerSettings?.allowInsecureHTTP == true ? .on : .off
        apiKey.stringValue = ""
        apiKey.placeholderString = providerSettings.flatMap {
            ProviderCredentialStore.key(for: $0.baseURL)
        } == nil ? local("填写 API 密钥或网关令牌", "Enter API key or gateway token")
                 : local("已保存密钥；留空继续使用", "Saved key available; leave blank to reuse")
        pendingApiKeyEnv = providerSettings?.apiKeyEnv ?? "DBABEL_API_KEY"
        pendingTimeout = providerSettings?.timeoutSeconds ?? 300
        apiTimeout.stringValue = String(pendingTimeout)
        apiProtocol.removeAllItems()
        apiProtocol.addItems(withTitles: ["Chat Completions / NewAPI", "Responses", "Anthropic Messages"])
        apiProtocol.selectItem(at: ["chat_completions", "responses", "anthropic_messages"].firstIndex(of: providerSettings?.effectiveAPIMode ?? "chat_completions") ?? 0)
        apiStream.title = local("流式返回（建议用于内网网关和推理模型）", "Stream responses (recommended for gateways and reasoning models)")
        apiStream.state = providerSettings?.stream == false ? .off : .on
        apiOmitTemperature.title = local("使用模型默认温度", "Use the model's default temperature")
        apiOmitTemperature.state = providerSettings?.temperatureMode == "omit" ? .on : .off
        apiOptions.stringValue = providerSettings?.requestOptionsJSON ?? ""
        apiOptions.placeholderString = #"{"thinking": {"type": "disabled"}}"#
        pendingMaxTokens = providerSettings?.maxOutputTokens
        pendingMaxBytes = providerSettings?.maxResponseBytes ?? 2_000_000
        apiBaseURL.placeholderString = "https://api.example.com/v1"
        apiModel.placeholderString = local("服务中可用的模型 ID", "Model ID available from your service")
        apiProviderPreset.removeAllItems()
        apiProviderPreset.addItems(withTitles: [local("自定义兼容服务／网关", "Custom compatible service / gateway")]
                                      + apiServicePresets.map(\.title))
        let savedIndex = apiServicePresets.firstIndex { $0.baseURL == apiBaseURL.stringValue }
        apiProviderPreset.selectItem(at: savedIndex.map { $0 + 1 } ?? 0)
        apiProviderPreset.target = self
        apiProviderPreset.action = #selector(providerPresetAction)
        populateModelPresets()
        apiStatus.stringValue = ""
        apiStatus.textColor = .systemRed
        apiStatus.maximumNumberOfLines = 0
        if !providerFieldConstraintsSet {
            for field in [apiBaseURL, apiModel, apiKey, apiProxy, apiTimeout, apiOptions] {
                field.translatesAutoresizingMaskIntoConstraints = false
                field.widthAnchor.constraint(equalToConstant: 550).isActive = true
            }
            providerFieldConstraintsSet = true
        }
        let sheet = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 610, height: 800),
                            styleMask: [.titled], backing: .buffered, defer: false)
        sheet.title = local("API 服务设置", "API service settings")
        sheet.appearance = window.appearance
        let explanation = NSTextField(wrappingLabelWithString: local(
            "选择 API 协议，填写服务地址、模型 ID 和密钥。NewAPI 使用 Chat Completions 和网关令牌。已有会话的审核不需要 API。",
            "Choose an API protocol, service URL, model ID and key. For NewAPI use Chat Completions and its gateway token. Reviewing a saved session needs no API."))
        explanation.textColor = .secondaryLabelColor
        let examples = NSTextField(wrappingLabelWithString: local(
            "支持基础地址或完整接口地址；NewAPI 通常填写 http(s)://网关地址/v1。公司内网服务需要先连接公司网络。",
            "Use a base URL or the full endpoint. NewAPI usually uses http(s)://gateway/v1. Connect to your company network before using internal services."))
        examples.textColor = .secondaryLabelColor
        apiProxy.placeholderString = local("仅在选用自定义代理时填写地址", "Enter URL only for a custom proxy")
        let jsonHelp = NSTextField(wrappingLabelWithString: local(
            "已有 Provider JSON 可导入；首次使用无需准备 JSON 文件。",
            "Import an existing Provider JSON if you have one. No JSON file is needed for first-time setup."))
        jsonHelp.textColor = .secondaryLabelColor
        let importButton = NSButton(title: local("导入 JSON…", "Import JSON…"),
                                    target: self, action: #selector(importProviderAction))
        let cancelButton = NSButton(title: local("取消", "Cancel"),
                                    target: self, action: #selector(cancelProviderAction))
        let saveButton = NSButton(title: local("保存设置", "Save settings"),
                                  target: self, action: #selector(saveProviderAction))
        saveButton.keyEquivalent = "\r"
        let testButton = NSButton(title: local("测试模型连接", "Test model connection"),
                                  target: self, action: #selector(testProviderAction))
        apiTestButton = testButton
        let buttons = row(importButton, testButton, NSView(), cancelButton, saveButton)
        buttons.distribution = .fill
        let stack = NSStackView(views: [
            label(local("连接 API 服务", "Connect an API service"), size: 24),
            explanation,
            label(local("接口协议", "API protocol")), apiProtocol,
            label(local("服务商预设（也可自填）", "Service preset (optional)")), apiProviderPreset,
            label(local("服务地址（Base URL）", "API base URL")), apiBaseURL,
            examples,
            apiTrustedHTTP,
            label(local("常见模型（也可自填）", "Suggested models (optional)")), apiModelPreset,
            label(local("模型 ID", "Model ID")), apiModel,
            label(local("API 密钥／网关令牌（保存在 macOS 钥匙串）",
                        "API key / gateway token (saved in macOS Keychain)")), apiKey,
            label(local("网络连接", "Network route")), apiProxyMode, apiProxy,
            apiStream, apiOmitTemperature,
            label(local("读取超时（秒，1–600；流式期间按无数据时长计算）", "Read idle timeout (seconds, 1–600)")), apiTimeout,
            label(local("模型附加参数 JSON（可选，以服务文档为准）", "Additional model parameters JSON (optional; follow service docs)")), apiOptions,
            jsonHelp,
            label(local("测试会发送一条简短请求，可能产生少量 API 用量。",
                        "Testing sends one short request and may incur a small amount of API usage.")),
        ])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 10
        stack.translatesAutoresizingMaskIntoConstraints = false
        let scroll = NSScrollView()
        scroll.drawsBackground = false
        scroll.hasVerticalScroller = true
        scroll.documentView = stack
        scroll.translatesAutoresizingMaskIntoConstraints = false
        let footer = NSStackView(views: [buttons, apiStatus])
        footer.orientation = .vertical
        footer.alignment = .leading
        footer.spacing = 8
        footer.translatesAutoresizingMaskIntoConstraints = false
        sheet.contentView?.addSubview(scroll)
        sheet.contentView?.addSubview(footer)
        NSLayoutConstraint.activate([
            scroll.topAnchor.constraint(equalTo: sheet.contentView!.topAnchor, constant: 18),
            scroll.leadingAnchor.constraint(equalTo: sheet.contentView!.leadingAnchor, constant: 30),
            scroll.widthAnchor.constraint(equalToConstant: 550),
            scroll.bottomAnchor.constraint(equalTo: footer.topAnchor, constant: -16),
            stack.widthAnchor.constraint(equalToConstant: 550),
            stack.leadingAnchor.constraint(equalTo: scroll.contentView.leadingAnchor),
            stack.topAnchor.constraint(equalTo: scroll.contentView.topAnchor),
            footer.leadingAnchor.constraint(equalTo: scroll.leadingAnchor),
            footer.widthAnchor.constraint(equalTo: scroll.widthAnchor),
            footer.bottomAnchor.constraint(equalTo: sheet.contentView!.bottomAnchor, constant: -18)
        ])
        providerSheet = sheet
        window.beginSheet(sheet)
    }

    private func populateModelPresets() {
        apiModelPreset.removeAllItems()
        let index = apiProviderPreset.indexOfSelectedItem - 1
        let models = apiServicePresets.indices.contains(index) ? apiServicePresets[index].models : []
        apiModelPreset.addItems(withTitles: [local("自定义模型 ID", "Custom model ID")] + models)
        apiModelPreset.selectItem(withTitle: apiModel.stringValue)
        if apiModelPreset.indexOfSelectedItem < 0 { apiModelPreset.selectItem(at: 0) }
        apiModelPreset.target = self
        apiModelPreset.action = #selector(modelPresetAction)
    }

    @objc private func proxyModeAction() {
        apiProxy.isEnabled = apiProxyMode.indexOfSelectedItem == 2
    }

    @objc private func providerPresetAction() {
        let index = apiProviderPreset.indexOfSelectedItem - 1
        if apiServicePresets.indices.contains(index) {
            apiBaseURL.stringValue = apiServicePresets[index].baseURL
            apiModel.stringValue = apiServicePresets[index].models.first ?? ""
        }
        apiProtocol.selectItem(at: apiServicePresets.indices.contains(index) && apiServicePresets[index].title.hasPrefix("Claude") ? 2 : 0)
        populateModelPresets()
    }

    @objc private func modelPresetAction() {
        if apiModelPreset.indexOfSelectedItem > 0 {
            apiModel.stringValue = apiModelPreset.titleOfSelectedItem ?? ""
        }
    }

    @objc private func importProviderAction() {
        guard let path = chooseFile(extensions: ["json"]) else { return }
        guard let data = try? Data(contentsOf: path),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              object["provider"] as? String == "openai-compatible",
              let baseURL = object["base_url"] as? String,
              let model = object["model"] as? String,
              let environment = object["api_key_env"] as? String else {
            apiStatus.stringValue = local("这不是有效的 OpenAI-compatible Provider JSON。",
                                          "This is not a valid OpenAI-compatible Provider JSON.")
            return
        }
        apiBaseURL.stringValue = baseURL
        apiModel.stringValue = model
        apiProviderPreset.selectItem(at: 0)
        populateModelPresets()
        pendingApiKeyEnv = environment
        pendingTimeout = object["timeout_seconds"] as? Int ?? 300
        apiTimeout.stringValue = String(pendingTimeout)
        apiProtocol.selectItem(at: ["chat_completions", "responses", "anthropic_messages"].firstIndex(of: object["api_mode"] as? String ?? "chat_completions") ?? 0)
        apiStream.state = (object["stream"] as? Bool ?? true) ? .on : .off
        apiOmitTemperature.state = object["temperature_mode"] as? String == "omit" ? .on : .off
        pendingMaxTokens = object["max_output_tokens"] as? Int
        if let body = object["extra_body"], let bytes = try? JSONSerialization.data(withJSONObject: body), let json = String(data: bytes, encoding: .utf8) { apiOptions.stringValue = json } else { apiOptions.stringValue = "" }
        pendingMaxBytes = object["max_response_bytes"] as? Int ?? 2_000_000
        apiTrustedHTTP.state = (object["allow_insecure_http"] as? Bool ?? false) ? .on : .off
        let importedProxyMode = object["proxy_mode"] as? String ?? "system"
        apiProxyMode.selectItem(at: ["system", "none", "custom"].firstIndex(of: importedProxyMode) ?? 0)
        proxyModeAction()
        apiStatus.textColor = .secondaryLabelColor
        apiStatus.stringValue = local("已导入 \(path.lastPathComponent)；请核对地址、模型和密钥后保存。",
                                      "Imported \(path.lastPathComponent). Check the URL, model and key, then save.")
    }

    @objc private func cancelProviderAction() {
        if let sheet = providerSheet { window.endSheet(sheet); sheet.orderOut(nil) }
        providerSheet = nil
        apiTestButton = nil
    }

    private func providerDraft() -> ProviderSettings {
        ProviderSettings(
            baseURL: apiBaseURL.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
                .trimmingCharacters(in: CharacterSet(charactersIn: "/")),
            model: apiModel.stringValue.trimmingCharacters(in: .whitespacesAndNewlines),
            apiKeyEnv: pendingApiKeyEnv,
            proxyURL: apiProxy.stringValue.trimmingCharacters(in: .whitespacesAndNewlines),
            timeoutSeconds: Int(apiTimeout.stringValue) ?? 0,
            maxResponseBytes: pendingMaxBytes,
            allowInsecureHTTP: apiTrustedHTTP.state == .on,
            proxyMode: ["system", "none", "custom"][max(0, min(2, apiProxyMode.indexOfSelectedItem))],
            apiMode: ["chat_completions", "responses", "anthropic_messages"][max(0, min(2, apiProtocol.indexOfSelectedItem))],
            stream: apiStream.state == .on,
            temperatureMode: apiOmitTemperature.state == .on ? "omit" : "auto",
            maxOutputTokens: pendingMaxTokens,
            requestOptionsJSON: apiOptions.stringValue.trimmingCharacters(in: .whitespacesAndNewlines))
    }

    @objc private func saveProviderAction() {
        let settings = providerDraft()
        if let error = settings.validationError() {
            apiStatus.textColor = .systemRed
            apiStatus.stringValue = error
            return
        }
        if !apiKey.stringValue.isEmpty {
            let result = ProviderCredentialStore.save(apiKey.stringValue, for: settings.baseURL)
            if result != errSecSuccess {
                apiStatus.textColor = .systemRed
                apiStatus.stringValue = local("无法把密钥保存到 macOS 钥匙串（\(result)）。",
                                              "Could not save the key to macOS Keychain (\(result)).")
                return
            }
            recentAPIKey = apiKey.stringValue
            recentAPIKeyBaseURL = settings.baseURL
        }
        do {
            UserDefaults.standard.set(try JSONEncoder().encode(settings),
                                      forKey: "DBabelProviderSettings.v1")
        } catch {
            apiStatus.textColor = .systemRed
            apiStatus.stringValue = error.localizedDescription
            return
        }
        providerSettings = settings
        providerName.stringValue = "\(settings.model) · \(settings.baseURL)"
        status.stringValue = local("API 服务已配置，可以开始翻译。", "API service configured; ready to translate.")
        cancelProviderAction()
        updateCurrentWorkbenchChat(settings)
    }

    private func updateCurrentWorkbenchChat(_ settings: ProviderSettings) {
        guard landingPage == .workbench,
              let workbenchURL = desktop.workbenchURL,
              let token = URLComponents(url: workbenchURL, resolvingAgainstBaseURL: false)?
                .fragment?.components(separatedBy: "token=").last,
              !token.isEmpty,
              let host = workbenchURL.host,
              host == "127.0.0.1" || host == "localhost" else { return }
        var endpoint = URLComponents(url: workbenchURL, resolvingAgainstBaseURL: false)!
        endpoint.path = "/api/chat/provider"
        endpoint.fragment = nil
        guard let url = endpoint.url else { return }
        let recentKey = recentAPIKeyBaseURL == settings.baseURL ? recentAPIKey : nil
        DispatchQueue.global(qos: .utility).async { [weak self] in
            let key = recentKey
                ?? ProviderCredentialStore.key(for: settings.baseURL)
                ?? ProcessInfo.processInfo.environment[settings.apiKeyEnv]
                ?? (settings.isLocal ? "local" : "")
            guard !key.isEmpty,
                  let configURL = try? settings.temporaryFile(),
                  let configData = try? Data(contentsOf: configURL),
                  let config = try? JSONSerialization.jsonObject(with: configData) as? [String: Any] else {
                DispatchQueue.main.async { [weak self] in
                    self?.status.stringValue = self?.local("聊天 API 配置未能载入。", "Could not load the chat API configuration.") ?? ""
                }
                return
            }
            try? FileManager.default.removeItem(at: configURL)
            guard let body = try? JSONSerialization.data(withJSONObject: ["config": config, "key": key]) else { return }
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.setValue(token, forHTTPHeaderField: "X-DBabel-Session")
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = body
            URLSession.shared.dataTask(with: request) { [weak self] _, response, error in
                DispatchQueue.main.async {
                    guard let self, self.desktop.workbenchURL == workbenchURL else { return }
                    if error == nil, (response as? HTTPURLResponse)?.statusCode == 200 {
                        self.browser?.evaluateJavaScript("window.dbabelRefreshChat?.()", completionHandler: nil)
                        self.status.stringValue = self.local("API 已连接到当前工作台聊天。", "API connected to this Workbench chat.")
                    } else {
                        self.status.stringValue = self.local("当前工作台聊天连接失败；请重新打开会话。",
                                                             "Chat connection failed; reopen the session.")
                    }
                }
            }.resume()
        }
    }

    @objc private func testProviderAction() {
        let settings = providerDraft()
        if let error = settings.validationError() {
            apiStatus.textColor = .systemRed
            apiStatus.stringValue = error
            return
        }
        let key = apiKey.stringValue.isEmpty
            ? (ProviderCredentialStore.key(for: settings.baseURL)
               ?? ProcessInfo.processInfo.environment[settings.apiKeyEnv] ?? "")
            : apiKey.stringValue
        if key.isEmpty && !settings.isLocal {
            apiStatus.textColor = .systemRed
            apiStatus.stringValue = local("请先填写 API 密钥或网关令牌。",
                                          "Enter the API key or gateway token first.")
            return
        }
        do {
            let provider = try settings.temporaryFile()
            apiTestButton?.isEnabled = false
            apiStatus.textColor = .secondaryLabelColor
            apiStatus.stringValue = local("正在发送测试请求…", "Sending a test request…")
            desktop.checkProvider(provider: provider,
                                  apiKey: key.isEmpty ? "local" : key,
                                  proxyURL: settings.proxyURL) { [weak self] success, detail in
                guard let self = self, self.providerSheet != nil else { return }
                self.apiTestButton?.isEnabled = true
                self.apiStatus.textColor = success ? .systemGreen : .systemRed
                self.apiStatus.stringValue = success
                    ? self.local("模型连接成功。", "Model connection succeeded.")
                    : String(detail.trimmingCharacters(in: .whitespacesAndNewlines).prefix(350))
            }
        } catch {
            apiStatus.textColor = .systemRed
            apiStatus.stringValue = error.localizedDescription
        }
    }

    @objc private func translateAction() { startTranslation(resumeRun: nil) }

    @objc private func resumeAction() {
        guard let run = matchingResumeRun() else {
            status.stringValue = local("未找到可继续的运行记录。", "No resumable run was found.")
            return
        }
        pendingResume = run
        source = run.source
        if let sourceItem = from.itemArray.first(where: { $0.representedObject as? String == run.sourceLanguage }),
           let targetItem = to.itemArray.first(where: { $0.representedObject as? String == run.targetLanguage }) {
            from.select(sourceItem)
            to.select(targetItem)
        } else {
            status.stringValue = local("上次运行的语言不在当前列表中。", "The saved languages are not in the current menu.")
            return
        }
        startTranslation(resumeRun: run.root)
    }

    private func startTranslation(resumeRun: URL?) {
        guard let source = source, let settings = providerSettings else {
            status.stringValue = local("请先选择原文并配置 API 服务。", "Choose a source and configure the API service first.")
            return
        }
        guard languagesAreValid() else { return }
        let configuredKey = (recentAPIKeyBaseURL == settings.baseURL ? recentAPIKey : nil)
            ?? ProviderCredentialStore.key(for: settings.baseURL)
            ?? ProcessInfo.processInfo.environment[settings.apiKeyEnv] ?? ""
        if configuredKey.isEmpty && !settings.isLocal {
            status.stringValue = local("请在 API 服务设置中填写密钥。", "Enter the API key in API service settings.")
            showProviderSheet()
            return
        }
        do {
            let provider = try settings.temporaryFile()
            let key = configuredKey.isEmpty && settings.isLocal ? "local" : configuredKey
            showProgress()
            desktop.translate(source: source, from: languageCode(from), to: languageCode(to),
                              role: role.stringValue, provider: provider,
                              apiKey: key, proxyURL: settings.proxyURL,
                              temporaryProvider: true, resumeRun: resumeRun)
        } catch {
            status.stringValue = error.localizedDescription
        }
        apiKey.stringValue = ""
    }
    @objc private func sessionAction() {
        if let bundle = chooseFile(extensions: [], directory: true) { desktop.openSession(bundle) }
    }
    @objc private func openSavedSessionAction(_ sender: NSButton) {
        guard let path = sender.identifier?.rawValue else { return }
        desktop.openSession(URL(fileURLWithPath: path))
    }
    @objc private func newTaskWindowAction() {
        let configuration = NSWorkspace.OpenConfiguration()
        configuration.createsNewApplicationInstance = true
        NSWorkspace.shared.openApplication(at: Bundle.main.bundleURL,
                                           configuration: configuration) { [weak self] _, error in
            if let error = error {
                DispatchQueue.main.async { self?.status.stringValue = error.localizedDescription }
            }
        }
    }
    @objc private func demoAction() { desktop.openDemo() }

    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if action.shouldPerformDownload {
            decisionHandler(.download)
        } else if let url = action.request.url,
                  url.scheme == "https" || (url.host != nil && url.host != "127.0.0.1") {
            NSWorkspace.shared.open(url)
            decisionHandler(.cancel)
        } else {
            decisionHandler(.allow)
        }
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        (webView as? MaterialWebView)?.allowWindowMaterialToShowThrough()
        webView.evaluateJavaScript("window.dbabelSetDesktopTheme?.('\(appearance.rawValue)')")
        guard landingPage == .workbench else { return }
        let icon = NSWorkspace.shared.icon(for: .folder)
        icon.size = NSSize(width: 32, height: 32)
        guard let tiff = icon.tiffRepresentation,
              let bitmap = NSBitmapImageRep(data: tiff),
              let png = bitmap.representation(using: .png, properties: [:]) else { return }
        let dataURL = "data:image/png;base64," + png.base64EncodedString()
        let script = """
        (() => { const old = document.getElementById('documentIcon'); if (!old) return;
          const image = document.createElement('img'); image.className = 'doc-icon-native';
          image.alt = ''; image.src = '\(dataURL)'; old.replaceWith(image); })()
        """
        webView.evaluateJavaScript(script)
    }

    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction,
                 didBecome download: WKDownload) { download.delegate = self }

    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for navigationAction: WKNavigationAction,
                 windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = navigationAction.request.url, url.scheme == "https" {
            NSWorkspace.shared.open(url)
        }
        return nil
    }

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let alert = NSAlert()
        alert.messageText = message
        alert.addButton(withTitle: local("确定", "OK"))
        alert.beginSheetModal(for: window) { _ in completionHandler() }
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let alert = NSAlert()
        alert.messageText = message
        alert.addButton(withTitle: local("继续", "Continue"))
        alert.addButton(withTitle: local("取消", "Cancel"))
        alert.beginSheetModal(for: window) { response in
            completionHandler(response == .alertFirstButtonReturn)
        }
    }

    func webView(_ webView: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String,
                 defaultText: String?, initiatedByFrame frame: WKFrameInfo,
                 completionHandler: @escaping (String?) -> Void) {
        let alert = NSAlert()
        alert.messageText = prompt
        alert.addButton(withTitle: local("保存", "Save"))
        alert.addButton(withTitle: local("取消", "Cancel"))
        let field = NSTextField(string: defaultText ?? "")
        field.frame = NSRect(x: 0, y: 0, width: 360, height: 26)
        alert.accessoryView = field
        alert.beginSheetModal(for: window) { response in
            completionHandler(response == .alertFirstButtonReturn ? field.stringValue : nil)
        }
    }

    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse,
                  suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = suggestedFilename
        completionHandler(panel.runModal() == .OK ? panel.url : nil)
    }

    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters,
                 initiatedByFrame frame: WKFrameInfo,
                 completionHandler: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        completionHandler(panel.runModal() == .OK ? panel.urls : nil)
    }
}

@main
struct DBabelApplication {
    static func main() {
        let application = NSApplication.shared
        let delegate = AppDelegate()
        application.delegate = delegate
        application.setActivationPolicy(.regular)
        application.run()
    }
}

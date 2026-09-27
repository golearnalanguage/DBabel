import AppKit
import Foundation
import Security
import WebKit

private final class FlippedView: NSView {
    override var isFlipped: Bool { true }
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
        if scheme == "http" && !isLocal {
            return "Remote API services require HTTPS. / 远程 API 服务需要 HTTPS。"
        }
        if url.path.hasSuffix("/chat/completions") {
            return "Enter the API base URL without /chat/completions. / 请填写服务的基础地址，不要包含 /chat/completions。"
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
        if !proxyURL.isEmpty {
            guard let proxy = URLComponents(string: proxyURL),
                  let proxyScheme = proxy.scheme?.lowercased(),
                  ["http", "https"].contains(proxyScheme),
                  proxy.host != nil, proxy.user == nil, proxy.password == nil,
                  proxy.query == nil, proxy.fragment == nil else {
                return "Enter an http(s) proxy URL such as http://127.0.0.1:1082. / 请填写 http(s) 代理地址，例如 http://127.0.0.1:1082。"
            }
        }
        return nil
    }

    func temporaryFile() throws -> URL {
        let path = FileManager.default.temporaryDirectory
            .appendingPathComponent("dbabel-provider-\(UUID().uuidString).json")
        let data = try JSONSerialization.data(withJSONObject: [
            "provider": "openai-compatible",
            "base_url": baseURL,
            "model": model,
            "api_key_env": apiKeyEnv,
            "timeout_seconds": timeoutSeconds,
            "max_response_bytes": maxResponseBytes
        ], options: [.prettyPrinted, .sortedKeys])
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

final class AppDelegate: NSObject, NSApplicationDelegate, NSToolbarDelegate, WKNavigationDelegate,
                         WKUIDelegate, WKDownloadDelegate {
    private let desktop = DesktopController()
    private var window: NSWindow!
    private var root: NSView!
    private var body: NSView!
    private var browser: WKWebView?
    private var currentURL: URL?
    private var source: URL?
    private var existingTarget: URL?
    private var providerSettings: ProviderSettings?
    private var pendingApiKeyEnv = "DBABEL_API_KEY"
    private var pendingTimeout = 120
    private var pendingMaxBytes = 2_000_000
    private var homeFieldConstraintsSet = false
    private var providerFieldConstraintsSet = false
    private var providerSheet: NSPanel?
    private var apiTestButton: NSButton?
    private var appearance: DesktopAppearance = .system
    private var chinese = true
    private var controls: [NSButton] = []
    private let status = NSTextField(labelWithString: "")
    private let sourceName = NSTextField(labelWithString: "")
    private let targetName = NSTextField(labelWithString: "")
    private let alignmentConfirmed = NSButton(checkboxWithTitle: "", target: nil, action: nil)
    private let providerName = NSTextField(labelWithString: "")
    private let apiBaseURL = NSTextField(string: "")
    private let apiModel = NSTextField(string: "")
    private let apiProxy = NSTextField(string: "")
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
        window.toolbarStyle = .unified
        let toolbar = NSToolbar(identifier: "DBabelToolbar")
        toolbar.delegate = self
        toolbar.displayMode = .iconOnly
        window.toolbar = toolbar
        buildMenus()
        let material = NSVisualEffectView(frame: window.contentView!.bounds)
        material.material = .underWindowBackground
        material.blendingMode = .behindWindow
        material.state = .active
        root = material
        window.contentView = root
        buildChrome()
        configureLanguageMenus()
        if let data = UserDefaults.standard.data(forKey: "DBabelProviderSettings.v1"),
           let saved = try? JSONDecoder().decode(ProviderSettings.self, from: data),
           saved.validationError() == nil {
            providerSettings = saved
        }
        showHome()
        desktop.onStatus = { [weak self] text in self?.status.stringValue = text }
        desktop.onBusy = { [weak self] busy in
            self?.controls.forEach { $0.isEnabled = !busy }
        }
        desktop.onWorkbench = { [weak self] url in self?.showWorkbench(url) }
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationWillTerminate(_ notification: Notification) { desktop.close() }

    private let homeItem = NSToolbarItem.Identifier("DBabelHome")
    private let providerItem = NSToolbarItem.Identifier("DBabelProvider")
    private let appearanceItem = NSToolbarItem.Identifier("DBabelAppearance")
    private let languageItem = NSToolbarItem.Identifier("DBabelLanguage")

    func toolbarDefaultItemIdentifiers(_ toolbar: NSToolbar) -> [NSToolbarItem.Identifier] {
        [providerItem, .flexibleSpace, homeItem, appearanceItem, languageItem]
    }

    func toolbarAllowedItemIdentifiers(_ toolbar: NSToolbar) -> [NSToolbarItem.Identifier] {
        [providerItem, .flexibleSpace, homeItem, appearanceItem, languageItem]
    }

    func toolbar(_ toolbar: NSToolbar, itemForItemIdentifier identifier: NSToolbarItem.Identifier,
                 willBeInsertedIntoToolbar flag: Bool) -> NSToolbarItem? {
        if identifier == appearanceItem {
            let item = NSMenuToolbarItem(itemIdentifier: identifier)
            item.label = "Appearance / 外观"
            item.image = NSImage(systemSymbolName: "circle.lefthalf.filled",
                                 accessibilityDescription: item.label)
            item.showsIndicator = false
            let menu = NSMenu(title: item.label)
            for (title, selector) in [
                ("Follow System / 跟随系统", #selector(appearanceSystemAction)),
                ("Light / 浅色", #selector(appearanceLightAction)),
                ("Dark / 深色", #selector(appearanceDarkAction))
            ] {
                let option = NSMenuItem(title: title, action: selector, keyEquivalent: "")
                option.target = self
                menu.addItem(option)
            }
            item.menu = menu
            return item
        }
        let item = NSToolbarItem(itemIdentifier: identifier)
        item.target = self
        if identifier == homeItem {
            item.label = "Home / 首页"
            item.image = NSImage(systemSymbolName: "house", accessibilityDescription: item.label)
            item.action = #selector(homeAction)
        } else if identifier == providerItem {
            item.label = "API Service / API 服务"
            item.image = NSImage(systemSymbolName: "network", accessibilityDescription: item.label)
            item.action = #selector(providerAction)
        } else if identifier == languageItem {
            item.label = "Language / 语言"
            item.image = NSImage(systemSymbolName: "globe", accessibilityDescription: item.label)
            item.action = #selector(languageAction)
        } else { return nil }
        return item
    }

    private func buildMenus() {
        let menu = NSMenu()
        let app = NSMenuItem()
        let appMenu = NSMenu(title: "DBabel")
        appMenu.addItem(withTitle: "Quit DBabel / 退出 DBabel",
                            action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        app.submenu = appMenu
        menu.addItem(app)
        let file = NSMenuItem()
        let fileMenu = NSMenu(title: "File / 文件")
        let browserOption = NSMenuItem(title: "Open in Browser / 在浏览器中打开",
                                       action: #selector(browserAction), keyEquivalent: "b")
        browserOption.target = self
        fileMenu.addItem(browserOption)
        file.submenu = fileMenu
        menu.addItem(file)
        let edit = NSMenuItem()
        let editMenu = NSMenu(title: "Edit / 编辑")
        for (title, action, key) in [
            ("Undo / 撤销", "undo:", "z"),
            ("Redo / 重做", "redo:", "Z"),
            ("Cut / 剪切", "cut:", "x"),
            ("Copy / 复制", "copy:", "c"),
            ("Paste / 粘贴", "paste:", "v"),
            ("Select All / 全选", "selectAll:", "a")
        ] {
            let item = NSMenuItem(title: title, action: Selector(action), keyEquivalent: key)
            item.target = nil
            editMenu.addItem(item)
        }
        edit.submenu = editMenu
        menu.addItem(edit)
        NSApp.mainMenu = menu
    }

    private func button(_ title: String, _ selector: Selector) -> NSButton {
        let value = NSButton(title: title, target: self, action: selector)
        value.bezelStyle = .rounded
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

    private func showHome() {
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
        let greeting = label("Happy you are here.", size: 44)
        greeting.font = NSFont.systemFont(ofSize: 44, weight: .medium)
        greeting.textColor = .labelColor
        status.lineBreakMode = .byWordWrapping
        status.maximumNumberOfLines = 0
        let stack = NSStackView(views: [
            greeting,
            row(label(local("翻译文档", "Translate a document"), size: 30),
                button(local("打开演示", "Open demo"), #selector(demoAction))),
            introduction,
            row(button(local("选择原文", "Choose source"), #selector(sourceAction)), sourceName),
            row(label(local("原文语言", "Source language")), from, label("→"),
                label(local("目标语言", "Target language")), to),
            row(label(local("文本角色", "Text role")), role),
            row(button(local("配置 API 服务", "Configure API service"), #selector(providerAction)), providerName),
            button(local("翻译并打开审核工作台", "Translate and open Workbench"), #selector(translateAction)),
            label(local("上传文档并建立审核会话", "Upload documents for review"), size: 22),
            uploadHelp,
            row(button(local("选择现有译文（可选）", "Choose existing target (optional)"), #selector(targetAction)),
                targetName, button(local("清除", "Clear"), #selector(clearTargetAction))),
            alignmentConfirmed,
            button(local("上传文档并打开工作台", "Upload documents and open Workbench"), #selector(uploadAction)),
            label(local("已有会话", "Existing session"), size: 22),
            button(local("打开 .dbreview 会话", "Open .dbreview session"), #selector(sessionAction)),
            status
        ])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 12
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
            stack.topAnchor.constraint(equalTo: content.topAnchor, constant: 32),
            stack.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 40),
            stack.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -40),
            stack.bottomAnchor.constraint(equalTo: content.bottomAnchor, constant: -32)
        ])
    }

    private func showWorkbench(_ url: URL) {
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

    @objc private func homeAction() { showHome() }
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
        if let menu = (window.toolbar?.items.first { $0.itemIdentifier == appearanceItem }
                       as? NSMenuToolbarItem)?.menu {
            for (index, option) in menu.items.enumerated() {
                option.state = index == [DesktopAppearance.system, .light, .dark]
                    .firstIndex(of: value) ? .on : .off
            }
        }
        browser?.evaluateJavaScript("window.dbabelSetDesktopTheme?.('\(value.rawValue)')")
    }
    @objc private func appearanceSystemAction() { setAppearance(.system) }
    @objc private func appearanceLightAction() { setAppearance(.light) }
    @objc private func appearanceDarkAction() { setAppearance(.dark) }

    @objc private func languageAction() {
        guard let browser = browser else { chinese.toggle(); showHome(); return }
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
        apiKey.stringValue = ""
        apiKey.placeholderString = providerSettings.flatMap {
            ProviderCredentialStore.key(for: $0.baseURL)
        } == nil ? local("填写 API 密钥或网关令牌", "Enter API key or gateway token")
                 : local("已保存密钥；留空继续使用", "Saved key available; leave blank to reuse")
        pendingApiKeyEnv = providerSettings?.apiKeyEnv ?? "DBABEL_API_KEY"
        pendingTimeout = providerSettings?.timeoutSeconds ?? 120
        pendingMaxBytes = providerSettings?.maxResponseBytes ?? 2_000_000
        apiBaseURL.placeholderString = "https://api.example.com/v1"
        apiModel.placeholderString = local("服务中可用的模型 ID", "Model ID available from your service")
        apiStatus.stringValue = ""
        apiStatus.textColor = .systemRed
        apiStatus.maximumNumberOfLines = 0
        if !providerFieldConstraintsSet {
            for field in [apiBaseURL, apiModel, apiKey, apiProxy] {
                field.translatesAutoresizingMaskIntoConstraints = false
                field.widthAnchor.constraint(equalToConstant: 550).isActive = true
            }
            providerFieldConstraintsSet = true
        }
        let sheet = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 610, height: 600),
                            styleMask: [.titled], backing: .buffered, defer: false)
        sheet.title = local("API 服务设置", "API service settings")
        sheet.appearance = window.appearance
        let explanation = NSTextField(wrappingLabelWithString: local(
            "连接支持 Chat Completions 的 API 服务。填写服务地址、可用模型 ID 和该服务签发的密钥。使用网关时填写网关令牌，不要填写上游渠道密钥。已有会话的审核不需要 API。",
            "Connect an API service that supports Chat Completions. Enter its base URL, available model ID and service-issued key. For a gateway, use its user token rather than an upstream channel key. Reviewing a saved session needs no API."))
        explanation.textColor = .secondaryLabelColor
        let examples = NSTextField(wrappingLabelWithString: local(
            "请使用服务文档给出的基础地址；本机服务可填 http://127.0.0.1:8000/v1。应用会追加 /chat/completions。",
            "Use the base URL from your service's documentation; a local service might use http://127.0.0.1:8000/v1. The app appends /chat/completions."))
        examples.textColor = .secondaryLabelColor
        apiProxy.placeholderString = "http://127.0.0.1:1082"
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
            label(local("服务地址（Base URL）", "API base URL")), apiBaseURL,
            examples,
            label(local("模型 ID（支持 Chat Completions）", "Model ID (Chat Completions)")), apiModel,
            label(local("API 密钥／网关令牌（保存在 macOS 钥匙串）",
                        "API key / gateway token (saved in macOS Keychain)")), apiKey,
            label(local("网络代理（可选；留空跟随系统）", "Network proxy (optional; blank uses system)")), apiProxy,
            jsonHelp,
            label(local("测试会发送一条简短请求，可能产生少量 API 用量。",
                        "Testing sends one short request and may incur a small amount of API usage.")),
            buttons, apiStatus
        ])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 10
        stack.translatesAutoresizingMaskIntoConstraints = false
        sheet.contentView?.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.topAnchor.constraint(equalTo: sheet.contentView!.topAnchor, constant: 22),
            stack.leadingAnchor.constraint(equalTo: sheet.contentView!.leadingAnchor, constant: 30),
            stack.widthAnchor.constraint(equalToConstant: 550),
            stack.bottomAnchor.constraint(lessThanOrEqualTo: sheet.contentView!.bottomAnchor,
                                          constant: -18)
        ])
        providerSheet = sheet
        window.beginSheet(sheet)
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
        pendingApiKeyEnv = environment
        pendingTimeout = object["timeout_seconds"] as? Int ?? 120
        pendingMaxBytes = object["max_response_bytes"] as? Int ?? 2_000_000
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
            timeoutSeconds: pendingTimeout,
            maxResponseBytes: pendingMaxBytes)
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

    @objc private func translateAction() {
        guard let source = source, let settings = providerSettings else {
            status.stringValue = local("请先选择原文并配置 API 服务。", "Choose a source and configure the API service first.")
            return
        }
        guard languagesAreValid() else { return }
        let configuredKey = ProviderCredentialStore.key(for: settings.baseURL)
            ?? ProcessInfo.processInfo.environment[settings.apiKeyEnv] ?? ""
        if configuredKey.isEmpty && !settings.isLocal {
            status.stringValue = local("请在 API 服务设置中填写密钥。", "Enter the API key in API service settings.")
            showProviderSheet()
            return
        }
        do {
            let provider = try settings.temporaryFile()
            let key = configuredKey.isEmpty && settings.isLocal ? "local" : configuredKey
            desktop.translate(source: source, from: languageCode(from), to: languageCode(to),
                              role: role.stringValue, provider: provider,
                              apiKey: key, proxyURL: settings.proxyURL,
                              temporaryProvider: true)
        } catch {
            status.stringValue = error.localizedDescription
        }
        apiKey.stringValue = ""
    }
    @objc private func sessionAction() {
        if let bundle = chooseFile(extensions: [], directory: true) { desktop.openSession(bundle) }
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

    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction,
                 didBecome download: WKDownload) { download.delegate = self }

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

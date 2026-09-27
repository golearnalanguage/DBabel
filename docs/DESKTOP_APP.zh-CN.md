# DBabel macOS 桌面应用

[English](DESKTOP_APP.md) · [文档目录](INDEX.zh-CN.md)

macOS 应用在原生窗口中打开现有的完整本地 Review Workbench。它可以运行 Provider 翻译流程、打开已有 `.dbreview` 会话，或打开独立演示副本。审核决定保存在会话目录中；应用不会自动批准译文。

## 安装和启动

已打包的 Apple Silicon 安装镜像位于 `output/release/DBabel-macOS-AppleSilicon.dmg`。打开镜像，将 **DBabel.app** 拖到“应用程序”后启动。打包命令在发布目录只保留一个应用和一个镜像，临时构建副本会清理。应用内含 Python 3.12、OpenSSL 3 和运行依赖；演示副本与新会话写入 `~/Library/Application Support/DBabel/`，不依赖原仓库或 `.venv`。这是本地临时签名、未公证的构建版，尚未制作面向公众的开发者签名安装包。

要从源码重建该安装镜像，需要 macOS、Apple Silicon、Xcode Command Line Tools 和用于下载构建依赖的网络连接。在本仓库执行：

```bash
cd /你的路径/DBabel
sh scripts/package_macos_app.sh
open output/release/DBabel-macOS-AppleSilicon.dmg
```

开发时也可用 `sh scripts/build_macos_app.sh` 构建依赖当前仓库的 `output/desktop/DBabel.app`。它优先使用已准备好的 `output/build-python` 与 `output/build-vendor`，其次使用仓库中的 `.venv`；仅运行 Swift 构建命令不会安装 Python 依赖。若尚未准备运行环境，可运行 `sh scripts/package_macos_app.sh` 制作自带依赖的安装版，或先在 `.venv` 中安装 `requirements-dev.txt`。macOS、Windows 和 Linux 仍可用 `python scripts/start_local.py` 启动浏览器版。

首页和内嵌工作台共用同一层 macOS 窗口材质。顶部右侧的三个按钮分别是**首页**、**外观**和**语言**；外观可选跟随系统、浅色、深色，地球按钮切换中文与英文。左侧的网络图标在首页和工作台中都能打开 **API 服务设置**。工作台通过 WebKit 可用的非公开画布开关透出窗口材质；制作 App Store 发布版前，需要复核或替换这项兼容处理。

## 翻译文档

选择 DOCX、TXT、Markdown 或 XLSX 原文。从下拉菜单选择不同的原文和目标语言，例如 `zh-CN` 与 `en`，再填写 `PROSE` 等具体文本角色。点击**配置 API 服务**，填写服务文档给出的基础地址、当前账户可用的模型 ID，以及该服务签发的 API 密钥。应用使用 OpenAI-compatible Chat Completions 请求，会在基础地址后追加 `/chat/completions`，所以地址栏中不要包含这段路径。远程服务必须使用 HTTPS；本机服务可以使用 `http://127.0.0.1:8000/v1` 这类地址。使用 API 网关时填写网关签发给用户的令牌，不要填写网关连接上游渠道时使用的密钥。

模型 ID 必须是所选服务已启用、当前密钥可访问、支持 Chat Completions 的模型。点击**测试模型连接**会通过翻译使用的同一代码路径发送一条简短请求，检查地址、密钥、模型路由和响应格式；测试可能产生少量 API 用量。若服务通过网关转发，还需确认网关中的上游渠道、模型映射和额度已经配置。

连接测试只验证 API，不解析所选文档。点击**翻译并打开审核工作台**后才会运行格式预检、提取和翻译。XLSX 使用内置提取器处理已存储的文本单元格；纯数字、日期、布尔值和公式保持原样，不作为翻译单元。文本单元越多，实际翻译与语义复核的请求和用量越多。若流程中止，首页会显示停止阶段和具体原因；检查额度前可先用一份小文档验收流程。

**网络代理**留空时使用 macOS 当前的系统代理；若服务必须经过单独的代理，可填写 `http://127.0.0.1:1082` 等实际地址。系统 VPN、公司内网 DNS 和代理仍须正常工作。出现 `TLS`、`SSL`、`Connection reset by peer` 或 `EOF` 时，请先检查网络、VPN 和代理：请求尚未到验证密钥或模型的阶段。`401` 表示令牌被拒绝，`403` 表示权限不足，`404` 通常是地址或模型，`429` 表示额度或速率限制。应用不会关闭证书验证来绕过连接错误。

首次使用无需创建 JSON 文件。若已有 OpenAI-compatible Provider JSON，可在设置窗口点击**导入 JSON…**；例如本机模型服务监听 `127.0.0.1:8000` 时：

```json
{
  "provider": "openai-compatible",
  "base_url": "http://127.0.0.1:8000/v1",
  "api_key_env": "DBABEL_API_KEY",
  "model": "your-model-id"
}
```

按实际服务修改模型名和地址。导入的 JSON 只预填设置；密钥仍需单独填写，或预先放入 JSON 中 `api_key_env` 指定的环境变量。点击**保存设置**后，应用把地址、模型和代理存入本机设置，把输入的密钥按服务地址存入 macOS 钥匙串。下次启动会沿用已保存的服务和密钥；密钥栏留空表示继续使用原密钥，输入新密钥并保存才会替换。密钥不会写入 Provider JSON 或仓库；临时配置文件不含密钥，使用后会删除。网关可能把本机请求转发给远程上游；最终去向取决于网关配置。已有本地会话的审核、QA 和导出无需连接 API 服务。

点击**翻译并打开审核工作台**。应用依次运行格式预检、生成译文建议、确定性 QA 与语义判定；只有达到 `READY_FOR_HUMAN_REVIEW` 才打开生成的会话。工作台仍要求明确的人工决定。配置原格式导出后，可在运行目录旁生成修订副本、回执、双语 HTML 和 Agent 交接记录。各格式的保真度和依赖见[格式说明](DOCUMENT_FORMATS.zh-CN.md)。

## 从首页上传文档审核

如果已有译文，或只想先建立本地审核会话，在首页同样先点**选择原文**，再到**上传文档并建立审核会话**区域选择现有译文（可选）。提供现有译文时，核对原译文单元顺序并勾选确认；点击**上传文档并打开工作台**，应用会预检文档、建立新的 `.dbreview` 会话并直接打开工作台。只上传原文时会保留原文作为未审核工作副本，不会调用 API 或自动生成译文。**打开演示**只用于体验示例数据，不是上传文档的前置步骤。

## 打开会话和离线审核

点击**打开 .dbreview 会话**选择会话目录，或点击**打开演示**。运行时创建的会话如原件仍存在，会从 `run.json` 恢复原文导出配置；上传创建的会话则使用 `inputs/` 中的原件副本。需要完整浏览器窗口时，可从菜单栏的**文件 → 在浏览器中打开**进入当前本地会话。

在工作台逐条对照原译文、记录决定、重新执行 QA，然后导出审核快照或原格式交付。原生窗口下载文件时会打开 macOS 保存面板。关闭应用会停止本地服务；再次打开保存的 `.dbreview` 目录即可续审。安装版的演示数据首次复制到 `~/Library/Application Support/DBabel/local-demo.dbreview`，以后启动不会覆盖已有决定；源码开发版使用 `output/local-demo.dbreview`。

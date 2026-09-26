# DBabel

**面向 AI Agent 的数据库术语核查与双语技术审校工具。**

DBabel 帮助团队按产品、版本和上下文核对技术译文。Agent 准备有定位的发现、证据和建议，审校人员在本地工作台确认修改，再导出经过完整性校验的 DOCX 副本与审核回执。

DBabel 提供审核流程、本地工具和格式适配器。用户提供文档与项目参考资料，Agent 生成译文并核实证据；工作台记录人工决策、运行检查并导出结果。

[English](README.md) · [工作流导航](docs/WORKFLOW_GUIDE.zh-CN.md) · [Agent 入口](SKILL.md) · [案例索引](examples/technical_translation_review_examples.zh-CN.md)

<p align="center"><picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/dbabel-logo-dark.svg">
  <img src="assets/dbabel-logo-light.svg" alt="DBabel Review Workbench" width="420">
</picture></p>

## 审核工作台

<p align="center"><img src="assets/dbabel-review-workbench-preview.png" alt="DBabel 工作台：对齐文本、证据与人工审核决策" width="100%"></p>

并排查看原文和译文，核对证据，然后明确选择**接受建议、保留当前译文、编辑、暂缓、阻断或豁免**。AI 建议、潜在问题和人工批准是不同状态。

- **界面语言**：右上角切换中文或英文，文档正文与审核备注保持原样。
- **逐条建议**：每个单元显示建议译文及理由，或具体的翻译、修改检查项。
- **集中审核**：按状态、问题类型、位置和标签筛选；选中一页或全部匹配项后，明确执行批量保留或暂缓。
- **分批交付**：Checkpoint 只应用已审核修改，未处理内容保持原样并列入回执。Final 仍要求完成全部必要审核。
- **人工修改后复核**：从 Reports 下载 Agent 交接报告，检查 typo、误用词和遗漏。将报告交给 Agent 执行复核，再由人工确认新建议。
- **离线协作**：Portable Review 可独立打开，导出人工决策后导入对应本地会话，再运行 QA。

在左侧 **上传文档** 中导入 TXT、Markdown、CSV/TSV、JSON/JSONL、HTML、DOCX、XLSX、PPTX 或带文字层的 PDF，先检查提取范围，再建立单语言或多目标语言会话。**术语 → 上传项目术语表** 支持 CSV/JSON 验证及适用范围内的术语符合率评分。

所有本地会话，包括演示和 review-only 会话，都可以导出 **JSON、CSV、TSV、Markdown、HTML、TXT** 审核结果。DOCX 原格式导出另行验证包结构与段落内容。详见[格式依赖与保真度](docs/DOCUMENT_FORMATS.md)。

## 工作流程

| 阶段 | 做什么 | 交给下一步的内容 |
|---|---|---|
| 准备 | 明确模式、语言、产品范围、可用资料和修订授权 | 任务上下文与资源计划 |
| 读取 | 预检真实格式、解析能力、实际覆盖范围与源目标对齐 | 有稳定位置的双语单元 |
| 判断 | 执行完整性检查、分析语义、核实证据 | 发现与建议译文 |
| 审核 | 人工明确记录接受、保留、修改或未决状态 | 已审核目标与待处理范围 |
| 复核 | 检查人工修改后的拼写和用词，再运行 QA | 需要再次确认的新建议 |
| 交付 | 导出阶段或完整 DOCX 副本并回读验证 | 输出文件与审核回执 |

按当前阶段加载文件，不预读整个资料库。[18 个案例](examples/technical_translation_review_examples.zh-CN.md)已分成五类独立文件，路由输出精确的 `example_files`。案例帮助诊断；当前文档结论使用对应产品与版本的证据。

## 启动本地演示

需要 Python 3.9+：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
mkdir -p output
.venv/bin/python -c "import shutil; shutil.copytree('examples/review_workbench_demo.dbreview', 'output/demo.dbreview')"
.venv/bin/python scripts/start_review_workbench.py output/demo.dbreview
```

演示副本支持审核和结果下载。真实文档可从“上传文档”开始，按[完整中文流程](docs/WORKFLOW_GUIDE.zh-CN.md)完成预检、建立会话、术语检查和导出。已有目标 DOCX 时，以 `--original target.docx --output reviewed.docx` 启动工作台启用原格式导出。每次试用请复制到新的输出目录。

## 交给 Agent 使用

### Codex

把下面这段发给 Codex：

```text
请将 https://github.com/golearnalanguage/DBabel 完整克隆到
~/.agents/skills/dbabel-database-terminology-audit，安装为本地 Codex Skill。入口是仓库根目录的 SKILL.md，请保留全部配套目录。
```

安装后，在技能选择器中找到 DBabel，上传待审文档，再发送：

```text
$dbabel-database-terminology-audit 请审查附件中的数据库术语。按文档中的产品和版本核对，列出问题位置、建议用词、修改理由和来源。
```

如果列表尚未更新，开启新会话或重启 Codex。

### Claude Code

```bash
mkdir -p "$HOME/.claude/skills"
git clone https://github.com/golearnalanguage/DBabel.git \
  "$HOME/.claude/skills/dbabel-database-terminology-audit"
```

然后在 Claude Code 中调用，把路径换成你的文档：

```text
/dbabel-database-terminology-audit 请审查 ./docs/database-manual.md 的数据库术语，列出问题位置、修改建议和依据。
```

### 其他 Agent

支持读取 GitHub 文件的 Agent 可以直接使用：

```text
请使用 https://github.com/golearnalanguage/DBabel 审查附件中的数据库术语。先读取 https://raw.githubusercontent.com/golearnalanguage/DBabel/main/SKILL.md。按 SKILL 的渐进加载流程执行：建立任务上下文；涉及文件时先预检真实格式与能力；只加载当前阶段需要的资源，不要预先读取全部 references；最终输出实际覆盖范围、有定位的发现、证据、真正执行过的 QA 和仍待确认的问题。
```

无法联网时，可下载并解压 [DBabel](https://github.com/golearnalanguage/DBabel/archive/refs/heads/main.zip)，把完整目录、待审文件和允许使用的参考资料一并交给 Agent。

## 审核与交付规则

- 核查术语、双语语义、受保护技术标记与项目用词；数据库运维和 SQL 调试不在此工作流内。
- 确定性 QA 检查占位符、路径、URL、数字、单位等完整性。`POTENTIAL_ISSUE` 需要判断；检查通过不等于语义正确。
- 保留产品、版本和文本角色的区别；证据不足时保留不确定性，不靠猜测修改。
- 原格式导出检查原文件哈希、目标锚点和回读文本，写入新副本并验证非目标文本不变；视觉版式检查仍需单独进行。
- 报告必须说明已检查范围、未决项与未执行检查。交换数据使用 DBabel JSON/CSV 合同；TBX、TMX 和 XLIFF 需要另行实现适配器。

## 开发与参考

当前仓库包版本为 **1.5.0**。Review Workbench 当前版本为 **1.5.0**。本工作树中的未发布改进见 [Changes](CHANGELOG.md)。

```bash
python -m py_compile scripts/*.py
python -m unittest discover -s tests -v
python scripts/check_package.py
```

有意修改包文件后，运行 `python scripts/check_package.py --write-manifest` 更新清单，再重新验证并执行 `git diff --check`。

[架构](docs/ARCHITECTURE.md) · [本地工具](docs/LOCAL_TOOLING.md) · [能力说明](docs/AGENT_CAPABILITY_MATRIX.md) · [人工修改后复核](docs/POST_REVIEW_QA.md) · [包索引](PACKAGE_INDEX.md) · [许可证](LICENSE)

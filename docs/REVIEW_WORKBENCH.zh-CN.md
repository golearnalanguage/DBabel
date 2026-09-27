# DBabel 审核工作台

[English](REVIEW_WORKBENCH.md) · [文档目录](INDEX.zh-CN.md)

Skill/包和工作台契约版本均为 **1.5.0**。版本字段不自动创建 Git 标签或 GitHub Release。初次使用请从[本地教程](WORKFLOW_GUIDE.zh-CN.md)开始；[格式矩阵](DOCUMENT_FORMATS.zh-CN.md)说明实际依赖和覆盖。

工作台连接原译文、建议、证据与人工决定。本地界面提供上传、术语检查、QA 和导出，便携 HTML 提供离线审阅。两者支持中英文界面。上传的单目标 DOCX/TXT/MD 会话自动配置原格式输出；仅原文输入仍是待翻译的工作副本。

## 审核与导出规则

- 建议不等于批准，确定性 `POTENTIAL_ISSUE` 不等于语义错误。
- `USER_EDITED` 在导出前重新检查。`UNREVIEWED`、`DEFERRED`、`BLOCKED` 阻止 FINAL；CHECKPOINT 保留其原有内容并列为待审。
- 确定性 ERROR 需解决，或由人明确选择 `WAIVED`、填写理由，并匹配当前问题指纹。
- 原件 SHA-256 须匹配会话；纳入原格式写入的单元须为 `ALIGNED`。其他对齐状态可以审核，但需专用回写路径。
- 原件不覆盖；通过回读和结构检查后才记录 `VERIFIED`。

## 会话文件

`.dbreview` 目录包含 `session.json`、`units.jsonl`、`issues.json`、`evidence.json`、`decisions.json`、`events.jsonl`、`anchors.json` 和 `original.sha256`。上传会话还保存 `inputs/` 副本和 `intake.json` 提取报告。术语表保存为 `project-glossary.csv` 或 `.json`。普通对齐会话记录原件名及哈希；仅 `--include-path-hint` 额外记录本地路径。

## DOCX 双语对齐

提取器按非空段落顺序配对并检查覆盖；数量不同不会猜测对应关系。拆分或合并应提供 `format_version: "1.0"` 的显式对齐映射，其 `alignments` 条目包含稳定 ID、从 1 开始的 `source`/`target` 段落索引和状态：

| 状态 | 对应关系 |
|---|---|
| ALIGNED | 一对一 |
| SPLIT | 一对多 |
| MERGED | 多对一 |
| UNALIGNED | 仅一侧有一个未匹配段落 |
| AMBIGUOUS | 两侧都有内容，需人工确定关系 |

每个非空段落须恰好出现一次；遗漏、重复、越界或状态与数量不符都会被拒绝。`alignment_id`、`source_refs`、`target_refs` 随单元保存。当前原格式回写仅接受 ALIGNED。

## 本地流程

```bash
python scripts/create_review_session.py units.jsonl --qa-report qa-report.json --audit-report audit-report.json --original translated.docx --output translated.dbreview
python scripts/start_review_workbench.py translated.dbreview --original translated.docx --output translated.reviewed.docx
```

服务器仅监听 `127.0.0.1`，使用随机会话令牌和浏览器安全响应头，前端无需外部运行时。保持终端打开，使用本次完整 URL。

## 便携审核

```bash
python scripts/build_portable_review.py translated.dbreview --output translated-review.html
python scripts/import_review_decisions.py translated.dbreview translated.docx.decisions.json
```

将导入命令中的文件名换成便携版实际下载的决策文件。生成的 HTML 自包含且不发网络请求。会话与版本校验防止将决定套到错误文件；导入后重新运行本地 QA，不能直接把便携状态当作原格式验收。

## 审阅操作

左侧选择页面并筛选单元；点击正文行打开右侧详情。核对原文、当前译文、建议原因、技巧和证据后，选择接受建议、保留当前、编辑、暂缓、阻断或豁免。编辑后保存文字，备注另行保存；批量操作先核对选中数量。技巧是诊断信息，不改变人工决定。没有完整建议时显示具体修改指引，不能接受不存在的翻译。

术语页上传 CSV/JSON，验证语言、范围和批准状态后计算适用检查的符合率。质量检查页运行新 QA。报告页生成 Agent 交接；设置页显示会话及输出条件。顶部可切换界面语言和主题、下载六种审核结果，HTML 提供双栏对照。

## 原格式交付

```bash
python scripts/export_reviewed_document.py translated.dbreview --original translated.docx --output translated.checkpoint-01.docx --export-mode CHECKPOINT
```

FINAL 是默认模式；CHECKPOINT 只应用已审核且通过检查的文字，待审内容保留。CLI 使用新名称，浏览器重复导出自动编号。下载 ZIP 包含原格式文件、回执、Markdown/JSON 交接和双语 HTML。导出校验原件、锚点和新 QA；DOCX 比较未修改部件和非文本 XML，TXT/MD 保留行结构。文字增长仍可能导致换行分页，需检查实际版面。

回执和交接记录列出修改、保持和未纳入单元；未纳入并非从文件中删除。人工修改后按[复核说明](POST_REVIEW_QA.zh-CN.md)让 Agent 返回绑定版本的建议，用户采纳后重新 QA 和导出。交接文件本身不执行模型，`NOT_RUN` 保留这一事实。

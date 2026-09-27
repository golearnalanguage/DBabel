# DBabel 中文使用流程

[English](WORKFLOW_GUIDE.md) · [文档目录](INDEX.zh-CN.md)

本指南面向本地审校人员，从上传原文开始，说明预检、建立会话、双语审核、QA、导出和 Agent 复核。先进入下载后的 DBabel 文件夹。示例使用合成内容；实际使用时替换文件路径。

## 1. 安装并准备独立演示副本

```bash
cd /Users/eric/Downloads/DBabel-submit
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
```

macOS/Linux 激活环境后运行下文命令：

```bash
source .venv/bin/activate
python scripts/start_local.py
```

上面的路径是本次项目位置，其他电脑请换成实际解压路径。Windows PowerShell 先用 `Set-Location "C:\你的目录\DBabel"` 进入项目，再用 `py -m venv .venv`、`.venv\Scripts\Activate.ps1`；后续 Python 命令相同。启动器首次复制演示到 `output/local-demo.dbreview`，以后继续该副本，不会重置已保存的审核。

macOS 还可[构建桌面应用](DESKTOP_APP.zh-CN.md)，在同一个原生毛玻璃窗口中打开演示或已有会话；工作台会跟随系统外观。

在任意目录也可以直接启动，无需记住当前终端在哪个文件夹：

```bash
/Users/eric/Downloads/DBabel-submit/.venv/bin/python /Users/eric/Downloads/DBabel-submit/scripts/start_local.py
```

依赖安装完成后，本地审核、术语检查、QA 和导出不需要联网或 API key。工作台本身不调用翻译模型；可手动编辑，也可将快照交给外部或本地 Agent 生成建议。首次安装依赖以及外部证据查询可能需要联网。

工作台会输出含会话令牌的本地 URL 并打开浏览器。右上角 **Language → 简体中文** 切换界面，主题可选浅色、深色或跟随系统。文档正文与审核备注不会随界面语言变化。

终端保持运行。重新打开时使用本次打印的完整 URL，包含 `#token=`；旧 URL 的令牌可能已失效。停止服务按 `Ctrl+C`。端口被占用时运行 `python scripts/start_local.py --port 8766`。提示找不到脚本时先检查目录，提示缺少模块时使用同一个 `.venv` Python 安装依赖。已有会话用 `python scripts/start_local.py --bundle /绝对路径/manual.en.dbreview`，数据会继续保存到该会话目录。

## 2. 上传原文与预检

左侧点击 **上传文档**，在“原文文档”选择文件，在“原文语言”填写 `zh-CN` 等语言标签，目标语言填写 `en` 或 `en,ja,de`。点击 **预检文档** 查看识别格式、单元数、哈希和提取限制。支持的依赖与提取范围见[格式说明](DOCUMENT_FORMATS.zh-CN.md)。

已有译文时可同时上传一个目标文档，并核对两侧单元的顺序和数量。确认一一对应后勾选对齐确认框；数量不同的文档应先交由 Agent 建立对齐映射。仅上传原文时，工作台建立待翻译单元，由 Agent 提供对应目标语言的译文。

只有一种目标语言且输入为 DOCX、TXT、MD 或 XLSX 时，当前译文区先保留原文作为原格式工作副本，状态仍为未审核。手动编辑或接受真正的翻译建议后才能交付。多目标语言会话用于独立的各语言对照审核；需要多个原格式成品时，按语言分别建立单目标会话。

命令行可执行相同流程：

```bash
python -c "from pathlib import Path; Path('output/source.txt').write_text('主库发送归档日志。\n连接数上限为 1000。\n', encoding='utf-8')"
python scripts/intake_document.py output/source.txt --inspect
python scripts/intake_document.py output/source.txt \
  --source-language zh-CN --target-languages en,ja \
  --output output/manual.dbreview
python scripts/start_review_workbench.py output/manual.dbreview
```

## 3. 建立会话并让 Agent 提供译文

上传面板的 **建立会话** 会保存新 `.dbreview` 目录并打开它；原会话保留。上传的输入副本在新会话的 `inputs/`，提取报告在 `intake.json`。新会话路径会显示在通知中；默认位于启动会话同级的 `dbabel-sessions/` 目录。

将以下提示交给 Agent，并附上工作台导出的 JSON 快照：

```text
使用 $dbabel-database-terminology-audit 审核这份文档。
以 zh-CN 为原文语言，为 en 和 ja 分别提供技术手册式译文。
先读取 SKILL.md，按任务路由资料。保留每条记录的 id、location 和语言。
对每个单元给出 suggested_target 和 suggestion_reason，说明术语、条件、
否定或技术标记的处理。证据不足的项目写明待核实内容。
输出 aligned-units.json（source、target、suggested_target、suggestion_reason），
新建会话供人工审核，保留旧会话及其 decisions.json，不代替用户接受建议。
```

Agent 已提供对齐数据时运行：

```bash
python scripts/create_review_session.py aligned-units.json \
  --output output/agent-proposals.dbreview
python scripts/start_review_workbench.py output/agent-proposals.dbreview
```

`target` 表示当前译文，`suggested_target` 表示待接受的建议。来源或目标为空时，请保留真实状态；工作台会显示对应的翻译或修改指引。

## 4. 上传术语表并查看评分

左侧 **术语 → 上传项目术语表**，选择 CSV 或 JSON，再点击 **验证并使用术语表**。格式参考 `templates/project_glossary.csv` 和 `templates/project_glossary.json`。Word/PDF 术语文档先由 Agent 整理为此结构，确认语言、产品范围及批准状态后上传。

```bash
python scripts/validate_glossary.py templates/project_glossary.csv
python scripts/start_review_workbench.py output/agent-proposals.dbreview \
  --glossary templates/project_glossary.csv
```

评分为“通过的适用术语与单元检查数 / 全部适用检查数 × 100”。仅使用适用范围内的 `PROJECT_APPROVED` 条目；没有适用条目时显示暂无评分。它反映术语符合率，语义、拼写和表达另行复核。上传成功后术语表保存在当前会话中，后续编辑及 QA 使用同一文件。

## 5. 审核与 QA

`TRANSLATE` / `BILINGUAL_REVIEW` 在交给人工审核前，Agent 必须把确定性 QA 指向真实建议译文，并通过完整工作台交付门禁：

```bash
python scripts/prepare_review_qa.py aligned-units.json --mode TRANSLATE --output review-qa-units.jsonl --receipt qa-target-selection.json
python scripts/check_bilingual_integrity.py review-qa-units.jsonl --output qa-report.json
python scripts/create_review_session.py aligned-units.json --qa-report qa-report.json --audit-report audit-report.json --original source.xlsx --output output/proposals.en.dbreview --mode TRANSLATE
python scripts/validate_translate_delivery.py output/proposals.en.dbreview --qa-input review-qa-units.jsonl --qa-report qa-report.json --audit-report audit-report.json --surface full --output delivery-receipt.json
```

门禁必须返回 `READY_FOR_HUMAN_REVIEW`。Portable Review 不能替代完整本地 Workbench 的交付门禁。


按状态、问题类型、位置或标签筛选，点击行打开右侧详情。核对建议、原因、参考证据与术语后，选择接受建议、保留当前译文、编辑、暂缓、阻断或豁免。点击“编辑”后修改译文，再点击“保存修改”；备注单独点击“保存备注”。豁免须填写理由。

每个单元都有建议译文或具体修改指引。只有确实提供了 `suggested_target` 才能点击“接受建议”。可选择本页或全部匹配项，批量保留当前译文或暂缓。

在 **质量检查** 页点击 **重新运行 QA**。数值、路径、占位符和术语问题应结合原文解释；解决问题后再运行。Agent 提出的语言修改经人工确认后再写入。

## 6. 导出双语或多语言结果

在顶部选择 JSON、CSV、TSV、Markdown、HTML 或 TXT，点击 **下载审核结果**。review-only 和演示会话均可导出。结果包含各目标语言的原译文、审核状态和 QA 状态；未接受的建议不会替代有效译文。完整问题、证据、备注和版本信息用 JSON 保存。

```bash
python scripts/export_review_results.py output/manual.dbreview \
  --format json --output output/manual-review.json
python scripts/export_review_results.py output/manual.dbreview \
  --format csv --output output/manual-review.csv
```

## 7. 导出原格式副本与交接包

通过上传面板创建的单目标 DOCX/TXT/MD/XLSX 会话会自动使用 `inputs/` 中保存的原件副本建立导出配置。点击原格式导出可下载 ZIP，包含修订文件、回执、Markdown/JSON 交接记录和 HTML 双语对照。交接记录区分已改、保持和未纳入的单元；“未纳入”表示阶段版仍保留原文，不表示从文件中删除。

保留版式时只修改原有段落或行中的文字，不新建段落、表格或列表。DOCX 的样式、表格结构和未修改部件经过程序比对，但译文变长仍可能改变换行和分页；请在 Word 或 LibreOffice 核对。TXT/MD 保留换行符和空行，被修改行的 Markdown 标记也需检查。

已有源、目标 DOCX 时，先生成明确的双语对齐单元。相同段落数量仍需核对语义对应关系。分拆、合并等情况用[对齐映射](REVIEW_WORKBENCH.md#bilingual-docx-alignment)。

```bash
python scripts/extract_docx_bilingual_units.py source.docx target.docx \
  --source-language zh-CN --target-language en --output output/docx-units.jsonl
python scripts/create_review_session.py output/docx-units.jsonl \
  --original target.docx --output output/docx-review.dbreview
python scripts/start_review_workbench.py output/docx-review.dbreview \
  --original target.docx --output output/target.reviewed.docx
```

**阶段版 CHECKPOINT** 仅应用已审核修改，其余保持原样并在回执中列明；**最终版 FINAL** 要求全部必要审核完成。两者均检查原文件哈希、锚点和所选范围内的 QA，写入新文件并回读验证。不要复用已有输出文件名。

```bash
python scripts/export_reviewed_document.py output/docx-review.dbreview \
  --original target.docx --output output/target.checkpoint-01.docx \
  --export-mode CHECKPOINT --receipt output/checkpoint-01.json
```

## 8. Agent 复核与交付

在 **报告** 页下载 Agent 复核包，或执行：

```bash
python scripts/build_post_review_report.py output/docx-review.dbreview \
  --output output/post-review.json
```

将报告与 [Agent 复核说明](POST_REVIEW_QA.zh-CN.md) 交给 Agent，检查人工修改中的错字、误用、遗漏、否定和技术标记。Agent 返回定位、原文本、建议文本、理由及版本指纹；审核后修改，再运行 QA 和最终导出。报告中的 `NOT_RUN` 表示尚未执行 Agent 复核。可添加 `--format md` 输出可读交接说明，原格式导出已自动包含它。

离线审核使用 `scripts/build_portable_review.py` 生成 HTML；将其导出的决策通过 `scripts/import_review_decisions.py` 导入原会话后重新检查。详细命令见[工作台手册](REVIEW_WORKBENCH.md)。

## 按问题选择案例

[18 个案例](../examples/technical_translation_review_examples.zh-CN.md)涵盖上下文、语义、产品范围、保护内容和文档结构。按路由读取匹配案例，再使用当前文档和产品证据判断。大项目可按位置或标签分批审核与交付。

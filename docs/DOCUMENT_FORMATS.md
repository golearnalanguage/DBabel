# Document formats / 文档格式

DBabel separates **text intake**, **review-result export**, and **native document write-back**. The upload panel uses the same extractor as `scripts/intake_document.py`; the format probe and the extraction report are saved in `intake.json`.

DBabel 分别记录**文本提取**、**审核结果导出**和**原格式回写**。上传面板与 `scripts/intake_document.py` 使用同一提取器，格式探测及实际提取范围保存在 `intake.json`。

All tools require Python 3.9+ and `requirements-dev.txt` (PyYAML and jsonschema). Standard-library extraction adds no parser dependency. A single upload is limited to 16 MiB; an Office package may expand to at most 64 MiB, and an intake may contain at most 20,000 language/segment pairs.

所有工具需要 Python 3.9+ 和 `requirements-dev.txt` 中的 PyYAML、jsonschema。下表标注“标准库”的格式无需额外解析包。单个上传文件上限为 16 MiB，Office 解包总量上限为 64 MiB，一次导入最多建立 20,000 个语言与单元组合。

| Input / 输入 | Extractor / 依赖 | Coverage and fidelity / 提取范围与保真度 | Native write-back / 原格式回写 |
|---|---|---|---|
| TXT, Markdown | Python standard library / 标准库 | Non-empty UTF-8 lines with line numbers; Markdown syntax stays in text / 保留行号及非空行，Markdown 标记保持原样 | Review results only / 导出审核结果 |
| CSV, TSV | Python `csv` | All non-empty cells including headers, with row/column locations / 所有非空单元格及表头，保留行列位置 | Review results only; original table shape is not reconstructed / 不重建原表结构 |
| JSON, JSONL | Python `json` | String values with JSON Pointer paths; keys/numbers/booleans excluded / 按 JSON Pointer 提取字符串值，键名和数值等不参与翻译 | Review results only / 导出审核结果 |
| HTML | Python `HTMLParser` | Text nodes in source order, excluding script/style/template; no browser layout or translated attributes / 提取文本节点，跳过脚本和样式，不处理动态 DOM 或属性 | Review results only / 导出审核结果 |
| DOCX | Python ZIP + XML | Main-body paragraphs including tables; upload excludes headers, notes, drawings and revision interpretation / 上传提取正文及表格段落，页眉、注释、绘图和修订语义需补充检查 | Existing anchored adapter preserves OOXML package parts; field codes/revisions block changed paragraphs / 已有锚点适配器保留包结构，含域或修订的待改段落需先处理 |
| XLSX | Python ZIP + XML | Stored non-formula cells, including hidden sheets; no formulas, comments, charts or display formatting / 提取存储值及隐藏工作表，跳过公式、批注、图表和显示格式 | Review results only / 导出审核结果 |
| PPTX | Python ZIP + XML | Slide paragraph text in slide XML order; no notes, charts, masters, SmartArt or image text / 提取幻灯片 XML 段落，不含备注、图表、母版或图中文字 | Review results only / 导出审核结果 |
| PDF | Optional `pypdf`: `python -m pip install pypdf` | Text layer by page; inspect reading order and tables. Scans need prior OCR / 按页提取文字层，需核对阅读顺序；扫描件先做 OCR | Review results only; no PDF layout reconstruction / 不重建 PDF 版式 |
| XML, DOC/XLS/PPT, macro-enabled Office, ODF, images | Detected by the format probe; upload extractor unavailable / 可识别，上传提取器尚未实现 | Convert a copy or have an Agent produce located aligned units / 转换副本或由 Agent 提供带位置的对齐单元 | Requires a separate format writer / 需专用写入器 |

Text grammars overlap: a Markdown file can begin with HTML and a TSV can resemble CSV. After the probe confirms text content, the upload extractor parses the declared text grammar and records both the probe result and the selected format. Binary content is never interpreted as Markdown solely because of its extension.

文本格式可能重叠，例如 Markdown 以 HTML 开头、TSV 呈现 CSV 特征。提取器先确认文本内容，再按声明的文本语法解析，同时记录探测结果与所选格式；二进制文件不会仅凭扩展名被当成 Markdown。

## Review-result formats / 审核结果格式

Every local session, including review-only and demo sessions, exports JSON, CSV, TSV, Markdown, HTML and TXT. Each row includes its source, effective target, languages and decision status. Pending rows retain the current target; an unaccepted proposal never becomes the exported target. Multiple target languages are represented as separate rows with stable IDs.

所有本地会话，包括 review-only 和演示会话，都可以导出 JSON、CSV、TSV、Markdown、HTML、TXT。每条结果保留原文、当前有效译文、语言和审核状态。待审核单元沿用当前译文，未接受的建议不会成为有效译文；多种目标语言用独立行和稳定 ID 表示。

- **JSON:** complete snapshot with decisions, revisions, suggestions, issues and evidence; preferred for Agent work / 完整快照，适合 Agent 复核。
- **CSV/TSV:** rectangular bilingual or multilingual review table; cells beginning with spreadsheet formula characters receive an apostrophe / 双语或多语言审核表；公式样式文本增加单引号，防止电子表格执行。
- **Markdown/TXT/HTML:** readable source/target records with locations and review/QA states; HTML content is escaped / 可读的原译文记录，包含位置和审核、QA 状态，HTML 正文经过转义。

These are review snapshots, not declarations of final approval. For final or checkpoint DOCX copies, use the [Workbench export gate](REVIEW_WORKBENCH.md#docx-native-export). Text round-trip checks verify content; inspect layout in Word or a renderer before publication.

审核快照可在任何阶段下载。最终版或阶段版 DOCX 副本使用[工作台导出检查](REVIEW_WORKBENCH.md#docx-native-export)。文本回读验证内容一致性；发布前在 Word 或渲染工具中检查版式。

# 原格式导出评估

[English](NATIVE_EXPORT_ASSESSMENT.md) · [格式矩阵](DOCUMENT_FORMATS.zh-CN.md)

为在现有文档中替换审核后的文字并保留结构，当前实现直接修改原文件包副本，不从提取段落重建文档。原件保持不变，每次交付使用新名称并附回执。本次未引入第三方文档写入器。

## 开源候选项目

| 项目 | 已核实许可与来源 | 评估 |
|---|---|---|
| [python-docx](https://github.com/python-openxml/python-docx) | [MIT](https://github.com/python-openxml/python-docx/blob/master/LICENSE) | 适合操作 Word，但 [Paragraph.text 官方说明](https://python-docx.readthedocs.io/en/latest/api/text.html)指出整段赋值会替换文字区段并移除区段格式，不符合本次保留要求。未复制代码。 |
| [Open XML SDK](https://github.com/dotnet/Open-XML-SDK) | [MIT](https://github.com/dotnet/Open-XML-SDK/blob/main/LICENSE) | 可作为后续 .NET Office 适配和 OOXML 校验候选。它不提供 Word 分页引擎，当前有限范围写入无需第二套运行时。未复制代码。 |
| [Okapi OpenXML Filter](https://okapiframework.org/wiki/index.php/OpenXML_Filter) | 已查阅官方过滤器说明，未选定组件 | 提取和合并架构适合翻译流程。接入前需选版本、核对组件许可并完成双语往返测试；目前不是依赖，也未验证其保真度。 |

评估日期：2026-09-27。这是架构适用性评估，尚非性能对比。后续若分发第三方组件，应保留适用许可和声明，并在 `THIRD_PARTY_NOTICE.md` 及包清单记录版本与依赖。

## 保留范围

DOCX 沿用原 ZIP 条目和可识别命名空间的 XML 字节位置。只修改选中的 `w:t` 文字及必要的 `xml:space` 属性，保留文字区段、段落和表格属性、命名空间前缀、注释、关系及其他部件。验证时屏蔽允许的文字变化，再对比其余 XML 字节；未修改部件须完全一致。ZIP 压缩后的字节可能不同。签名、宏内容以及无法明确定位或不支持的锚点会阻止回写；新增段落、制表符和手动换行需专用处理。

跨样式区段的替换沿用原区段位置，新词跨越粗体或斜体边界时应检查样式对应关系。正文及表格提取并不表示页眉、脚注或图片文字已审核，实际范围在导入报告中记录。Strict OOXML 和不支持的编码需单独适配。

TXT/MD 按锚点替换 UTF-8 行，保留 BOM、混合换行符、空行和未修改行。被修改行中的 Markdown 标记由审核者核对。双语 HTML 是额外的审核文件，采用自己的对照版式。

XLSX 使用稳定的 `xl/worksheets/sheetN.xml:CELL` 单元格锚点处理已存储的非公式单元格。已批准修改只替换副本中对应 `<c>` 元素；所有未触及 OOXML 部件内容必须逐字节一致，已修改工作表除批准单元格元素外不得变化。公式单元格直接阻断回写。共享字符串或富文本单元格修改后会写为 inline string，因此单元格内部富文本 runs 不保证保留，必须目视复核。工作簿关系、绘图、图表、批注、样式、数据验证等未触及部件不重建。


## 验收与后续格式

测试覆盖命名空间、样式区段、表格、媒体、页眉、精确替换、原件保护、重复文本、换行及阶段导出记录。每份正式交付文档仍需在 Word 或 LibreOffice 检查版面；目前没有代表性用户文件和渲染结果能证明分页完全一致。

XLSX 现已提供受限的已解析单元格写入器，并测试锚定替换、公式拒绝和未触及部件保真；被修改的富文本单元格及代表性客户工作簿仍需目视验证。PPTX 仍需验证文字区段、关系、文本框尺寸和溢出；PDF 需独立版式/OCR 流程，文字层替换不能保证原始可编辑文件的保真度。PPTX/PDF 在专用写入器通过检查前仍仅导出审核结果。

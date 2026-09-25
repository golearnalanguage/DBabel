# 工作流导航：这一步做什么，下一步找什么

从 `SKILL.md` 开始。只读取当前阶段需要的文件；案例不能替代当前产品证据。

| 阶段 | 输入与动作 | 对应入口 | 完成后 / 遇到问题时 |
|---|---|---|---|
| 1. 明确任务 | 确定模式、语言、产品/版本、允许使用的资料和修订授权 | `scripts/prepare_runtime.py` | 缺失信息保留未知，不猜测；生成任务上下文 |
| 2. 文件预检 | 按实际内容检查格式与可用解析能力 | `scripts/preflight_document.py`、`references/17_RUNTIME_PREFLIGHT_AND_INGEST_VALIDATION.md` | READY 才解析；不支持则报告阻碍 |
| 3. 最小加载 | 按任务与风险路由 | `scripts/route_resources.py`、`config/resource_router.yaml` | 只读 `load_now` 与 `example_files`，状态改变时重新路由 |
| 4. 解析与对齐 | 保留稳定位置，记录未读取结构，建立源/目标对应 | `scripts/validate_ingest.py`；DOCX 用 `scripts/extract_docx_bilingual_units.py` | 对齐歧义回到结构检查；不静默丢弃内容 |
| 5. 发现与判断 | 完整性检查后进行语义判断，核实范围和证据 | `scripts/build_translation_review_intake.py`、`references/03_TERMINOLOGY_CLASSIFICATION.md` | POTENTIAL_ISSUE 不是错译结论；按下表找案例 |
| 6. 人工审核 | 创建会话，逐条或按筛选批量记录人工决策 | `scripts/create_review_session.py`、`scripts/start_review_workbench.py`、`docs/REVIEW_WORKBENCH.md` | 修改立即重检；未处理项保持原状态 |
| 7. 阶段交付 | 导出已批准修改，其他内容保留原样 | `scripts/export_reviewed_document.py --export-mode CHECKPOINT` | 回执列出未审核 ID；不能称为完整发布 |
| 8. 人工修改后复核 | 导出带版本指纹的报告，让 Agent 检查 typo、误用、遗漏 | `scripts/build_post_review_report.py`、`docs/POST_REVIEW_QA.md` | 建议返回人工审核；不自动接受，不复用过期文本 |
| 9. 完整发布 | 全部必要审核完成，阻断项解决，执行新 QA、写入副本并回读 | `scripts/export_reviewed_document.py --export-mode FINAL` | 保存回执；任何新修改回到第 6 步 |

## 按问题选择案例

| 问题 | 类别目录 | 案例 |
|---|---|---|
| 标题与步骤矛盾、执行主机范围、操作对象错位 | `examples/cases/context/` | A1、A2、A3 |
| 否定例外、前置条件、数值单位、技术主张、NULL | `examples/cases/semantics/` | B1–B5 |
| 跨产品概念、版本改名、项目用词与精确 UI 标签 | `examples/cases/product-scope/` | C1–C3 |
| 标识符与正文混淆、OCR 字符、占位符绑定 | `examples/cases/protected-content/` | D1–D3 |
| PDF 顺序、表格公式、图形角色、HTML 可译属性 | `examples/cases/document-structure/` | E1–E4 |

具体文件链接见 [案例索引](../examples/technical_translation_review_examples.zh-CN.md)。没有实质匹配就不加载；一次最多三例。一个问题涉及多个维度时仍要避免重复报告。

## 大项目怎么分批

按 Location、Tag、问题类型或审核状态筛选。勾选一页后可以选择所有匹配项，再明确执行批量 Keep Current / Defer。Keep Current 会保留原译文并重新执行 QA，不等于接受全部 AI 建议。

阶段 DOCX 仍是完整文件，但只有已审核目标被改动。未审核内容、已暂缓或阻断内容原样保留；导出回执的 `review_scope` 列出边界。已审核范围内的未豁免 ERROR、锚点错误、原文件变化仍然阻断导出。无已审核项时不生成空阶段交付。阶段交付不是完整质量认证。

工作台原生写回目前仅支持 DOCX。网站、HTML 和其他大规模输入可以分批审核、下载复核报告或离线决策包；不能把它们描述为已支持原格式写回。

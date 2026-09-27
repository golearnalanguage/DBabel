# Agent 接入

[English](AGENT_INTEGRATION.md) · [文档目录](INDEX.zh-CN.md)

将完整仓库放入名为 `dbabel-database-terminology-audit` 的技能文件夹，保留相对目录结构。`SKILL.md` 是执行契约，定义任务选择、命名和交付要求；支持资料按 `config/resource_router.yaml` 渐进加载。安装和调用入口见 [README](../README.zh-CN.md)。

## 执行顺序

纯文本任务先建立上下文并路由资料。文件任务依次检查真实格式、解析能力，建立最小资源计划，读取 `load_now`，运行提取器，验证实际覆盖，再继续术语或翻译审核。对齐、证据、授权或范围变化时重新路由。

```bash
python scripts/prepare_runtime.py --mode AUDIT --file manual.docx --declare-backend native_agent --output runtime-plan.json
python scripts/validate_ingest.py ingest-report.json
```

`READY_FOR_INGEST` 说明具备开始提取的条件，不代表已提取。报告须说明检查了哪些结构、哪些仍未检查。公开来源验证需要检索并打开原始页面；原格式修订需要适用写入器和往返检查，能力见[矩阵](AGENT_CAPABILITY_MATRIX.zh-CN.md)。

## 技巧路由与正式判断

`suggest_translation_techniques.py` 按明确的触发信号、任务模式和文本用途匹配技巧，不从自由文本自动推断语义。`extract_translation_signals.py` 仅提取白名单中的表面线索，并记录来源侧、检测器、匹配文本和位置；语言缺失时不会猜测语言规则。

`build_translation_review_intake.py` 汇总信号、技巧候选和确定性 QA。TRANSLATE 中没有译文时形成 PRE_TRANSLATION，待译文生成再做双语 QA；已有译文进入 ADJUDICATION。候选技巧、QA 结果和人工批准各自独立，语义判断完成后才能写正式 finding 的 technique 元数据。

规格行可使用 `SCANNABLE_SPECIFICATION_PRESENTATION`，先保留对象、数值、单位、比较关系、建议/必须及范围，再改善扫读。其书籍和官方资料依据见[研究依据](RESEARCH_BASIS.zh-CN.md)。

## 命名和建议契约

单目标会话用 `manual.en.dbreview`，多目标用 `manual.multilingual.dbreview`。每个原文与目标语言组合使用独立稳定 ID。`target` 保存当前文本；`suggested_target` 保存待接受建议，`suggestion_reason` 说明具体理由。

```json
{"id":"U00001_en","location":"line:1","source_language":"zh-CN","target_language":"en","source":"主库发送归档日志。","target":"","suggested_target":"The primary database sends archived logs.","suggestion_reason":"保留主库作为动作主体，采用项目已批准术语。"}
```

每个单元必须有完整译文建议或具体修改指引。信息不足时指出需要核实的问题和来源。继续已有会话时保留人工决定与备注，新建建议会话或返回绑定版本的建议，不用 Agent 编写的接受状态替换 `decisions.json`。

保留版式的原格式会话应每种目标语言各建一份。仅上传 DOCX/TXT/MD 原文时，当前文本保留原文供定位，仍未翻译和批准；新建建议会话时必须使用同一原件和准确当前文本作为锚点。详细人机交接提示见 [SKILL](../SKILL.md) 和[本地教程](WORKFLOW_GUIDE.zh-CN.md)。

## 审核、交付和维护

人完成审核后生成[复核交接](POST_REVIEW_QA.zh-CN.md)，Agent 提交建议，用户决定是否采用，再运行 QA。CHECKPOINT 保留未审内容并列明范围；FINAL 检查完整审核。原格式输出附回执、双语 HTML、Markdown/JSON 交接说明；其他格式可导出带状态的审核快照。

结构化报告使用 `schemas/audit_report.schema.json`，运行 `python scripts/validate_report.py report.json`。校验器检查记录契约，外部来源需实际打开，输出需实际回读。Git 安装更新使用 `git -C <技能目录> pull --ff-only`，先保留本地修改；每台主机保留一份安装，避免重复技能条目。

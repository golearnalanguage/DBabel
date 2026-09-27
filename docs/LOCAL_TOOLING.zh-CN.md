# 本地工具

[English](LOCAL_TOOLING.md) · [文档目录](INDEX.zh-CN.md)

本地脚本提供路由、格式预检、术语、确定性 QA、覆盖和报告契约，结构化结果供 Agent 阅读来源与判断语义。先按[本地教程](WORKFLOW_GUIDE.zh-CN.md)进入项目并安装 Python 3.9+ 和 `requirements-dev.txt`。以下命令在项目根目录且虚拟环境已激活时运行。可选解析器不会自动安装。

## 启动与导入

```bash
python scripts/start_local.py
python scripts/intake_document.py source.md --inspect
python scripts/intake_document.py source.md --source-language zh-CN --target-languages en,ja --output manual.multilingual.dbreview
python scripts/start_local.py --bundle manual.multilingual.dbreview
```

启动器也可使用绝对脚本路径。上传面板采用同一提取流程；术语页接受标准 CSV/JSON。多语言会话保留每种目标语言的独立单元，原格式输出逐语言建会话。

## 运行计划、格式和能力

```bash
python scripts/prepare_runtime.py --mode LOOKUP
python scripts/prepare_runtime.py --mode AUDIT --file manual.docx --declare-backend native_agent --output runtime-plan.json
python scripts/detect_document_format.py manual.docx
python scripts/probe_capabilities.py --declare native_agent
python scripts/preflight_document.py manual.docx --intent audit --declare-backend native_agent
```

运行计划结合格式、声明或可用能力、任务上下文及初始资源计划。`READY_FOR_INGEST` 表示可以开始提取，之后须记录覆盖。扩展名与内容冲突或格式未核实时，不能自动选择解析器。

## 术语、双语 QA 和报告

`TRANSLATE` / `BILINGUAL_REVIEW` 禁止直接把 source-only 的原文锚点送入双语 QA。先生成真实审核目标：

```bash
python scripts/prepare_review_qa.py aligned-units.json --mode TRANSLATE --output review-qa-units.jsonl --receipt qa-target-selection.json
```

建会话时必须绑定 `--qa-report` 和 `--audit-report`，再验证完整本地工作台交付：

```bash
python scripts/validate_translate_delivery.py project.en.dbreview --qa-input review-qa-units.jsonl --qa-report qa_report.json --audit-report audit-report.json --surface full --output delivery-receipt.json
```

门禁通过只表示 `READY_FOR_HUMAN_REVIEW`，不代表最终完成。


```bash
python scripts/validate_glossary.py project_glossary.csv
python scripts/check_bilingual_integrity.py bilingual_units.jsonl --glossary project_glossary.csv --output qa_report.json
python scripts/validate_ingest.py ingest-report.json
python scripts/validate_report.py examples/audit_report.json
```

术语仅对范围与语言匹配的 `PROJECT_APPROVED` 条目执行。双语单元须预先对齐；QA 输出是 `POTENTIAL_ISSUE`，不代替语义结论或授权。覆盖报告 PASS 不能含未检查结构，PARTIAL 须列出缺口，FAIL 表示提取尚未达到所需范围。报告校验检查数据契约，来源真实性和渲染版式分别核对。

## 交付与人工修改后复核

```bash
python scripts/export_review_results.py manual.multilingual.dbreview --format html --output manual.review.html
python scripts/start_review_workbench.py project.dbreview --original target.docx --output reviewed.docx
python scripts/start_review_workbench.py project.dbreview --original target.xlsx --output reviewed.xlsx
python scripts/export_reviewed_document.py project.dbreview --original target.docx --output checkpoint-01.docx --export-mode CHECKPOINT
python scripts/build_post_review_report.py project.dbreview --format md --output post-review.md
```

CLI 导出使用新文件名。默认 FINAL 要求完整审核，CHECKPOINT 保留待审文字。原格式支持 DOCX/TXT/MD 以及已解析单元格锚点的 XLSX，附回执、双语 HTML 和 Markdown/JSON 交接；PPTX/PDF 等其他格式见[矩阵](DOCUMENT_FORMATS.zh-CN.md)。`NOT_RUN` 代表 Agent 尚未复核，执行步骤见[复核说明](POST_REVIEW_QA.zh-CN.md)。

## 开发与包校验

```bash
python -m py_compile scripts/*.py
python -m unittest discover -s tests -v
python scripts/check_documentation.py
python scripts/check_package.py
git diff --check
```

有意修改包文件后执行 `python scripts/check_package.py --write-manifest` 再重验。不要将用户本地 demo 决策写入发布清单；先用干净发布副本校验。工作台上传只送到经令牌验证的本地服务；输入和提取报告保存在会话中。Agent 或外部解析服务按任务实际授权访问资料。

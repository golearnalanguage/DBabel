# 文档目录

[English](INDEX.md)

| 任务 | 中文手册 | 英文手册 |
|---|---|---|
| 安装、本地启动和人工审核 | [本地教程](WORKFLOW_GUIDE.zh-CN.md) | [Walkthrough](WORKFLOW_GUIDE.md) |
| 构建并使用 macOS 应用 | [桌面应用](DESKTOP_APP.zh-CN.md) | [Desktop app](DESKTOP_APP.md) |
| 审核状态、对齐和便携版 | [工作台](REVIEW_WORKBENCH.zh-CN.md) | [Workbench](REVIEW_WORKBENCH.md) |
| 格式依赖和保真度 | [格式说明](DOCUMENT_FORMATS.zh-CN.md) | [Formats](DOCUMENT_FORMATS.md) |
| 原格式实现及开源评估 | [实现评估](NATIVE_EXPORT_ASSESSMENT.zh-CN.md) | [Assessment](NATIVE_EXPORT_ASSESSMENT.md) |
| Agent 安装、命名和建议 | [Agent 接入](AGENT_INTEGRATION.zh-CN.md) | [Integration](AGENT_INTEGRATION.md) |
| 各项功能的能力和前提 | [能力矩阵](AGENT_CAPABILITY_MATRIX.zh-CN.md) | [Capabilities](AGENT_CAPABILITY_MATRIX.md) |
| 人工修改后的复核 | [复核说明](POST_REVIEW_QA.zh-CN.md) | [Post-review QA](POST_REVIEW_QA.md) |
| 命令行工具 | [本地工具](LOCAL_TOOLING.zh-CN.md) | [Local tools](LOCAL_TOOLING.md) |
| 设计和数据流 | [架构](ARCHITECTURE.zh-CN.md) | [Architecture](ARCHITECTURE.md) |
| 出版书籍和官方资料 | [研究依据](RESEARCH_BASIS.zh-CN.md) | [Research](RESEARCH_BASIS.md) |
| 已实现和后续工作 | [路线图](ROADMAP.zh-CN.md) | [Roadmap](ROADMAP.md) |

## 语言组织规则

`docs/` 下的当前用户手册成对维护：`.md` 为英文，`.zh-CN.md` 为简体中文，分别介绍同一工作流程，不逐段交错翻译。命令、标识符、实际界面标签和原译文案例保留原始语言。

`SKILL.md`、schema、配置和按需加载的 `references/` 是统一的 Agent/运行时契约，保留单一版本以避免执行说明冲突；中文解释放在 Agent 接入手册。历史发布说明、仓库治理文件及原始案例集保留标明的原始语言。[英文案例索引](../examples/technical_translation_review_examples.md)注明中文案例集和本次完整配对的数值规格案例。新增或大幅修改用户手册时须补齐语言入口和链接，发布前执行 `python scripts/check_documentation.py`。

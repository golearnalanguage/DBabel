# Documentation

[简体中文](INDEX.zh-CN.md)

| Need | English | Simplified Chinese |
|---|---|---|
| Install, run locally and review | [Walkthrough](WORKFLOW_GUIDE.md) | [本地教程](WORKFLOW_GUIDE.zh-CN.md) |
| Build and use the macOS app | [Desktop app](DESKTOP_APP.md) | [桌面应用](DESKTOP_APP.zh-CN.md) |
| Workbench states, alignment and portable review | [Workbench](REVIEW_WORKBENCH.md) | [工作台](REVIEW_WORKBENCH.zh-CN.md) |
| Format dependencies and fidelity | [Formats](DOCUMENT_FORMATS.md) | [格式说明](DOCUMENT_FORMATS.zh-CN.md) |
| Original-format implementation and open-source evaluation | [Assessment](NATIVE_EXPORT_ASSESSMENT.md) | [实现评估](NATIVE_EXPORT_ASSESSMENT.zh-CN.md) |
| Agent setup, naming and proposals | [Integration](AGENT_INTEGRATION.md) | [Agent 接入](AGENT_INTEGRATION.zh-CN.md) |
| What each capability can do | [Capabilities](AGENT_CAPABILITY_MATRIX.md) | [能力矩阵](AGENT_CAPABILITY_MATRIX.zh-CN.md) |
| Review human edits | [Post-review QA](POST_REVIEW_QA.md) | [人工修改后复核](POST_REVIEW_QA.zh-CN.md) |
| Command-line tools | [Local tools](LOCAL_TOOLING.md) | [本地工具](LOCAL_TOOLING.zh-CN.md) |
| Design and data flow | [Architecture](ARCHITECTURE.md) | [架构](ARCHITECTURE.zh-CN.md) |
| Published/official sources | [Research](RESEARCH_BASIS.md) | [研究依据](RESEARCH_BASIS.zh-CN.md) |
| Implemented and planned work | [Roadmap](ROADMAP.md) | [路线图](ROADMAP.zh-CN.md) |

## Language policy

Current user manuals under `docs/` have paired files: `.md` for English and `.zh-CN.md` for Simplified Chinese. They present equivalent workflows without alternating translated paragraphs. Commands, identifiers, actual UI labels and source/target examples retain their original language.

`SKILL.md`, schemas, configuration and routed `references/` are canonical Agent/runtime contracts, maintained once to prevent contradictory instructions; Chinese explanations live in the integration guide. Historical release notes, repository governance files and original diagnostic case collections retain their labeled source language. The [English case index](../examples/technical_translation_review_examples.md) identifies the Chinese case corpus and a fully paired numerical-specification case. New or substantially revised user manuals must have both language entries and valid local links. Run `python scripts/check_documentation.py` before release.

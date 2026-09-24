# DBabel

**面向 AI Agent 的数据库术语核查与技术本地化 QA Skill。**

DBabel 由 **DB（Database，数据库）**与 **Babel（巴别塔）**组合而成，目标是在
不抹平产品、版本和语境差异的前提下连接不同语言中的数据库概念。它帮助译者、
技术写作者、数据库团队和 AI Agent 核查术语、审查双语内容、执行技术翻译，
并在满足条件时生成可复核的修订副本。

DBabel 采用“轻数据、重方法”的设计。仓库提供工作流、Schema、验证器、路由规则、
合成测试和可选格式适配器，但**不内置厂商术语库**。项目术语表、客户资料和参考文档
仍然是用户或项目自行提供的运行时输入。

[English](README.md) · [Skill Kernel](SKILL.md) · [Package Index](PACKAGE_INDEX.md)

## 安装和使用

### Codex

把下面这段发给 Codex：

```text
请将 https://github.com/golearnalanguage/DBabel 完整克隆到
~/.agents/skills/dbabel-database-terminology-audit，安装为本地 Codex Skill。
入口是仓库根目录的 SKILL.md，请保留全部配套目录。
```

安装后，在技能选择器中找到 DBabel，上传待审文档，再发送：

```text
$dbabel-database-terminology-audit 请审查附件中的数据库术语。
按文档中的产品和版本核对，列出问题位置、建议用词、修改理由和来源。
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
请使用 https://github.com/golearnalanguage/DBabel 审查附件中的数据库术语。
先读取 https://raw.githubusercontent.com/golearnalanguage/DBabel/main/SKILL.md。
按 SKILL 的渐进加载流程执行：建立任务上下文；涉及文件时先预检真实格式与能力；
只加载当前阶段需要的资源，不要预先读取全部 references；最终输出实际覆盖范围、
有定位的发现、证据、真正执行过的 QA 和仍待确认的问题。
```

无法联网时，可下载并解压 [DBabel](https://github.com/golearnalanguage/DBabel/archive/refs/heads/main.zip)，
把完整目录、待审文件和允许使用的参考资料一并交给 Agent。

## 渐进式运行模型

DBabel 不要求 Agent 每次都先读完整套规则，而是根据当前状态逐层加载：

```text
用户请求
  → Task Context
  → 文件格式/能力预检（如适用）
  → Resource Router
  → 只加载 load_now
  → 实际解析 + 覆盖范围验证
  → 术语 / 翻译工作流
  → 已完成双语对齐时才运行确定性 QA
  → 语义裁决
  → 已授权时才进入修订门禁
  → Round-trip QA
  → 输出
```

状态变化后会重新路由。例如，原文和译文尚未对齐时不会提前加载确定性双语 QA；
未获得修订授权时不会提前加载修订专用规则；已有项目内批准资料可以解决问题且用户
没有要求外部核验时，也不会无条件加载公开检索流程。

详见 [Agent Integration](docs/AGENT_INTEGRATION.md)、
[Architecture](docs/ARCHITECTURE.md) 和 [Local Tooling](docs/LOCAL_TOOLING.md)。

## Accuracy Core

Accuracy Core 提供可重复的确定性检查，用来补充语义审校，而不是替代语义判断。

目前包括：

- 项目术语表 JSON Schema 与 CSV 模板；
- JSON/CSV 术语表验证与统一规范化；
- 只对当前作用域内的 `PROJECT_APPROVED` 词条执行确定性约束；
- 受保护字面量、占位符、URL、路径、文件名、CLI 参数、环境变量、版本、数字及数字/单位完整性检查；
- 输出分类为 `POTENTIAL_ISSUE` 的确定性双语 QA 报告。

验证项目术语表：

```bash
python scripts/validate_glossary.py project_glossary.csv
```

对已经完成对齐的双语单元执行 QA：

```bash
python scripts/check_bilingual_integrity.py \
  bilingual_units.jsonl \
  --glossary project_glossary.csv \
  --output qa_report.json
```

需要特别区分：

```text
POTENTIAL_ISSUE
≠ 已确认错译
≠ 技术证据
≠ HIGH confidence
≠ 自动修订授权
```

真正的术语结论仍然要经过上下文、作用域、证据和裁决。

## 文件预检与可选后端

对于文件任务，DBabel 把以下四件事严格区分：

```text
扩展名声称的格式
≠ 文件内容实际格式
≠ 解析器当前可用
≠ 文件已经成功且完整解析
```

默认格式探针只使用 Python 标准库，并采用有界、非执行式检查。它可以识别常见 magic
signature、ZIP/OLE/OOXML 容器和宏启用 Office 包；如果扩展名与实际内容冲突，会 fail
closed，而不是静默挑选解析器。

生成文件任务运行计划：

```bash
python scripts/prepare_runtime.py \
  --mode AUDIT \
  --file ./docs/manual.docx \
  --declare-backend native_agent \
  --output runtime-plan.json
```

真正解析完成后，再验证实际覆盖范围：

```bash
python scripts/validate_ingest.py ingest-report.json
```

可选 detector/parser 只登记能力，不会自动安装。安装第三方依赖前请先查看
[Format Backends](plugins/FORMAT_BACKENDS.md)。

## 常用任务

- **术语查询**：核对指定产品、版本和句子中的术语含义与用法。
- **文档审查**：检查文件中的术语、产品范围、技术标记和上下文一致性。
- **双语审查**：对齐原文与译文后，检查术语、遗漏、数字和受保护内容。
- **技术翻译**：结合项目术语表生成译文，并完成确定性与语义复检。
- **文档修订**：仅对已授权且满足修订门禁的发现写入副本，随后重新打开并复检。

例如：

```text
$dbabel-database-terminology-audit 请结合附件术语表，将 manual-zh.md 翻译成英文。
保留 SQL、配置项、路径和产品名，另存为新文件，完成术语复检并列出待确认项。
```

## 输出结果

| 结论 | 含义 |
|---|---|
| `KEEP` | 当前用词适合该语境 |
| `REPLACE` | 有依据支持具体修改 |
| `PROTECT` | 保留原样的名称或技术标记 |
| `REVIEW` | 需要补充资料或人工判断 |
| `OUT_OF_SCOPE_CLAIM` | 需要另行核实的技术事实陈述 |

文件任务必须区分已检查与未检查的结构。预检成功不代表解析成功，确定性 QA 无问题也不
代表语义完全正确，保存成功也不代表修订结果已经通过 round-trip QA。

## 本地验证

当前仓库包版本为 **1.4.0**。

Python 3.9+：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python scripts/check_package.py
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/validate_report.py examples/audit_report.json
.venv/bin/python scripts/validate_glossary.py tests/fixtures/project_glossary.json
.venv/bin/python scripts/validate_glossary.py tests/fixtures/project_glossary.csv
.venv/bin/python scripts/check_bilingual_integrity.py \
  tests/fixtures/bilingual_units.jsonl \
  --glossary tests/fixtures/project_glossary.json \
  --output /tmp/dbabel-qa.json
```

通过本地 validator 只说明相应机器契约满足要求，并不自动证明外部来源真实、语义判断
正确或文件覆盖完整。

[Changes](CHANGELOG.md) · [许可证](LICENSE) · [能力说明](docs/AGENT_CAPABILITY_MATRIX.md)

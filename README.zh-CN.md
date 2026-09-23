# DBabel

**面向 AI Agent 的数据库术语核查 Skill。**

DBabel 由 **DB（Database，数据库）**与 **Babel（巴别塔）**组合而成，
寓意连接数据库领域的不同语言。它帮助译者、技术写作者和数据库团队结合产品、
版本与上下文核查术语，让文档中的用词准确、一致、有据可查。

你可以用它查询术语、审查文档、比对双语内容、翻译技术资料，也可以生成修订副本。
每项重要修改都会附上位置、理由和依据，便于复核。

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

在终端安装：

```bash
mkdir -p "$HOME/.claude/skills"
git clone https://github.com/golearnalanguage/DBabel.git \
  "$HOME/.claude/skills/dbabel-database-terminology-audit"
```

在 Claude Code 中调用，把文件路径换成你的文档：

```text
/dbabel-database-terminology-audit 请审查 ./docs/database-manual.md 的数据库术语，列出问题位置、修改建议和依据。
```

### 其他 Agent

支持读取 GitHub 文件的 Agent 可以直接使用：

```text
请使用 https://github.com/golearnalanguage/DBabel 审查附件中的数据库术语。
先读取 https://raw.githubusercontent.com/golearnalanguage/DBabel/main/SKILL.md，
再按任务需要读取该仓库中的配套文件。
结合产品、版本和上下文核对术语，输出问题位置、修改建议、理由和来源；
对于暂时无法确认的术语，说明还需要哪些资料。
```

无法联网时，下载并解压 [DBabel](https://github.com/golearnalanguage/DBabel/archive/refs/heads/main.zip)，
把整个文件夹、待审文档及参考资料交给 Agent，明确让它读取文件夹中的 `SKILL.md`。

## 常用任务

安装后，可在调用名称后直接说明任务：

- **术语查询**：核对某个术语在指定产品、版本和句子中的含义与用法。
- **双语审查**：提供原文和译文，检查术语、产品名、缩写与技术标记。
- **技术翻译**：提供原文、目标语言和项目术语表，生成译文并完成术语复检。
- **文档修订**：要求将证据充分的修改写入副本，返回修订文件、修改清单与复检结果。

例如，在 Codex 中：

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

文档审查会说明实际覆盖范围；修订后会重新打开文件，核对修改和非目标内容。
详细流程见 [SKILL.md](SKILL.md)，工具要求见[能力说明](docs/AGENT_CAPABILITY_MATRIX.md)。

[English](README.md) · [本地验证](README.md#validation) · [许可证](LICENSE)

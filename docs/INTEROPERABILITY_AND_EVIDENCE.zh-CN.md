# TMX 格式交换与本地证据缓存

[English](INTEROPERABILITY_AND_EVIDENCE.md) · [文档目录](INDEX.zh-CN.md)

这些命令为既有审核流程生成本地材料。TMX 导入产生待审核候选，证据检查定位需要复核的范围；两者都保留 `.dbreview` 的人工决策。

## TMX 1.4

在选定的 Python 环境安装可选集成依赖：

```bash
python -m pip install -r requirements-integration.txt
```

将现有本地记忆导出到新 TMX 文件：

```bash
python scripts/tmx_exchange.py export --memory --output memory.tmx
```

导出器使用记忆视图同一个 `runtime.translation_memory.export_entries()` 接口。源文、译文、语言标签保留原值，`x-dbabel-record` 属性保存已有文本角色、作用域、原决策元数据和来源字段。默认排除被拒绝的译文；`--include-rejected` 可连同 DBabel 状态保留它们以供检查，其他 CAT 工具可能忽略该状态，因此这种文件应作为检查材料。也可用 `--entries entries.json` 导出明确给出的 JSON 列表。已有输出文件会被保护。

为精确语言对生成候选回执：

```bash
python scripts/tmx_exchange.py import incoming.tmx --source-language en --target-language zh-CN --output candidates.json
```

读取范围是无命名空间、`version="1.4"`、各一个 header/body，以及纯文本 `<seg>`。语言标签按所选语言精确对应，邻近地区变体需另行选择。重复或缺失语言、未知扩展和行内元素会产生 `UNSUPPORTED` 候选；完整单元及片段 XML 保存在 `provenance`，未解析的行内内容对应文本字段为 null。可读的纯文本候选也保持 `USER_REVIEW`，外部文件的批准状态仅保存在来源元数据。缺失作用域保留为空，缺失文本角色记为 `UNKNOWN`。

输入沿用文档接收的 16 MiB 上限，拒绝 XML 实体声明，关闭外部 DTD、实体和网络加载。当前提供纯文本片段交换 CLI，候选回执供另行开展带作用域的人审；行内代码重建、TMX 全部方言、TBX/XLIFF 和工作台/记忆数据库导入仍需后续适配。其他 CAT 工具可能删掉自定义属性，交换回来后应先检查元数据。

## 证据来源快照

准备一个符合既有[证据契约](../schemas/evidence.schema.json)的记录、可读本地来源文件及 JSON 作用域对象。按任务填入项目、产品、版本、文本角色等已知事实；空字段保留未知范围。

```bash
python scripts/evidence_cache.py record --cache /absolute/path/evidence-cache --evidence evidence.json --source opened-reference.txt --scope scope.json --unit-id U001 --expires-at 2026-12-01T00:00:00Z
python scripts/evidence_cache.py check --cache /absolute/path/evidence-cache --scope current-scope.json --session project.dbreview --output evidence-check.json
```

`record` 校验证据记录，保留以 SHA-256 标识的私有来源快照及经过完整性校验的不可变记录。多个依赖单元可重复使用 `--unit-id`。来源定位、权威/语境/版本判断和既有证据状态保持原值；相同输入复用同一记录。来源及缓存记录都受 16 MiB 上限约束。有效期可选，时间需明确时区。

`check` 检查当前本地来源内容、已保存快照的完整性、显式有效期，以及调用者提供的当前作用域。来源变化、来源缺失、作用域变化或过期会报告 `STALE`、具体原因与受影响单元 ID；`source_evidence_state` 保留原来的 `CONFLICTING` 或 `INSUFFICIENT` 等判断。`--session` 读取 `units.jsonl` 的证据引用以补充受影响单元，人工决策、备注、QA 与会话证据文件保持原样。

检查退出码为：所有记录保持 CURRENT 时 `0`，存在需复核记录时 `2`，数据错误、快照/记录篡改或读写失败时 `1`。报告写入新路径。本地哈希对应已提供来源字节是否变化；网页实时更新、语义权威及当前作用域仍需对应复核。依赖发生变化后，重新打开有关来源，和审校人员检查受影响建议，再运行适用的 QA 与导出检查。

缓存包含本地来源材料，应选择仓库之外的目录，和私有项目文件一起保存并纳入用户备份。命令不访问网址或密钥；打包时应排除项目缓存。

## 采用项目与验证

XML 读写使用 lxml。记忆相似候选、官方 SDK 和开发验证工具的锁定版本、用途及原始许可见[第三方声明](../THIRD_PARTY_NOTICE.md)。REA、OmegaT、Translate Toolkit 和 Okapi 在这里提供架构或格式参考，相关命令未内嵌其源码。

[机器可读组件登记](../config/third_party_components.json) 与 Python 精确依赖及 Node 锁定版本交叉检查。准备发行时可以保留实际安装材料的许可和声明：

```bash
python scripts/check_third_party.py
python scripts/check_third_party.py --installed --distribution-path /absolute/site-packages --output output/license-inventory
```

清单保留许可原文字节、wheel 原生库声明及 SHA-256 回执。退出码 `2` 表示元数据、安装版本差异或缺失声明需复核，工具会记录缺口。选定目录之外的独立 Python/OpenSSL 运行时与浏览器二进制仍需单独盘点；输出目录必须为新路径。

定向验证命令：

```bash
python -m unittest discover -s tests -p 'test_tmx_exchange.py' -v
python -m unittest discover -s tests -p 'test_evidence_cache.py' -v
```

TMX 测试需要 lxml，仅核心依赖环境会跳过；集成环境应实际运行全部 TMX 测试。证据缓存测试沿用核心校验依赖。

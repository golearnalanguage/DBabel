# 本地预检查与翻译记忆

[English](LOCAL_PRECHECK_AND_MEMORY.md)

调用 AI 前，DBabel 先在本地提取支持的文本，统计审核单元、重复原文、受保护技术标记、疑似原文错字位置和精确记忆匹配。这些步骤不消耗 API token，也不判断语义正确性或批准译文。

macOS 的记忆库位于 `~/Library/Application Support/DBabel/translation-memory.sqlite3`，审核变更后写入一致性备份 `translation-memory.backup.sqlite3`。它按原文、语言组合和适用范围索引人工接受、修改、拒绝记录。范围包含 `project_id`、厂商、产品、版本、领域和文本角色；缺失元数据按未知处理。需要同一项目跨文档复用时，在对齐单元中填写 `context.project_id`，或运行 `run_project.py --project-id`。未指定项目 ID 时，原件或原文的 SHA-256 形成 `document:<sha256>` 文档范围。

同一范围的精确批准匹配优先作为 REVIEW 建议复用，不调用模型；用户仍需结合上下文审核。拒绝约束与同原文联动决定也遵守此范围。原 `.dbreview` 会话仍是审核记录的权威来源。旧库迁移前保存 `translation-memory.pre-scope-v1.sqlite3`；旧记录标为 `LEGACY_UNSCOPED`，继续提供管理和导出，暂停自动复用与拒绝约束。

安装可选 RapidFuzz 集成后，所选单元还会显示「相似的已批准译文」，列出相似度、原文差异和范围，供手动修改参考，权限为 `SUGGESTION_ONLY`。[本地工具](LOCAL_TOOLING.zh-CN.md#可选集成)说明安装方式。

左侧「术语」页可查看、编辑、删除和导出记忆条目。JSON 导出含原文、译文、语言组合、范围、文本角色、决定和时间；编辑记忆库不会改写原审核决定或自动批准之后的单元。可选 [TMX 交换](INTEROPERABILITY_AND_EVIDENCE.zh-CN.md)可导出范围化记忆，或导入带来源的待审核候选。

此页也提供默认关闭的数据库通用术语参考，以及可下载的术语识别模板。参考库不是项目批准术语，不强制执行术语 QA；模板条目默认 USER_REVIEW，用户批准后才具有相应效力。

`DBABEL_TRANSLATION_MEMORY`、`DBABEL_GENERAL_TERMS_SETTINGS` 和 `DBABEL_REJECTION_MEMORY` 可覆盖三类用户状态路径。单元测试用 `python scripts/run_tests.py` 自动隔离这三项。记忆库包含用户数据，应纳入用户备份，不得放入 App 安装包或 Git 仓库。

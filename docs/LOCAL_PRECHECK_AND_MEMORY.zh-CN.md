# 本地预检查与翻译记忆

[English](LOCAL_PRECHECK_AND_MEMORY.md)

调用 AI 前，DBabel 先在本地提取支持的文本，统计审核单元、重复原文、受保护技术标记、疑似原文错字位置和精确记忆匹配。这些步骤不消耗 API token，也不判断语义正确性或批准译文。

macOS 的记忆库位于 `~/Library/Application Support/DBabel/translation-memory.sqlite3`，审核变更后写入一致性备份 `translation-memory.backup.sqlite3`。它按原文、语言组合和文本角色索引人工接受、修改、拒绝记录。符合范围的精确批准匹配优先作为 REVIEW 建议复用，不调用模型；用户仍需结合上下文审核。拒绝过的译法会被排除。原文或文本角色不同不会自动匹配，原 `.dbreview` 会话仍是审核记录的权威来源。

左侧「术语」页可查看、编辑、删除和导出记忆条目。JSON 导出含原文、译文、语言组合、文本角色、决定和时间；编辑记忆库不会改写原审核决定或自动批准之后的单元。

此页也提供默认关闭的数据库通用术语参考，以及可下载的术语识别模板。参考库不是项目批准术语，不强制执行术语 QA；模板条目默认 USER_REVIEW，用户批准后才具有相应效力。

测试可用 `DBABEL_TRANSLATION_MEMORY` 和 `DBABEL_GENERAL_TERMS_SETTINGS` 隔离路径。记忆库包含用户数据，应纳入用户备份，不得放入 App 安装包或 Git 仓库。

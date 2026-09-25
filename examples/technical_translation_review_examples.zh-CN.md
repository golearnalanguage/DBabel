# 技术翻译案例索引

按当前问题加载对应文件，最多三个。案例是诊断模式，不是当前任务的证据。

先确定问题机制，再读取单个案例；未匹配时不加载。通用流程见 [工作流导航](../docs/WORKFLOW_GUIDE.zh-CN.md)。

### A1 标题写“导出”，实际步骤描述“导入”

[读取独立案例](cases/context/A1.zh-CN.md)

### A2 上级标题涵盖两台主机，不等于每一步都执行两次

[读取独立案例](cases/context/A2.zh-CN.md)

### A3 标题、按钮与正文指向不同操作对象

[读取独立案例](cases/context/A3.zh-CN.md)

### B1 否定、例外与“全部”同时丢失

[读取独立案例](cases/semantics/B1.zh-CN.md)

### B2 把前置校验移到操作之后

[读取独立案例](cases/semantics/B2.zh-CN.md)

### B3 数值相同，单位、默认值与作用范围已经变了

[读取独立案例](cases/semantics/B3.zh-CN.md)

### B4 术语修正与性能主张分别处理

[读取独立案例](cases/semantics/B4.zh-CN.md)

### B5 NULL、空字符串与“未知”被混成一个概念

[读取独立案例](cases/semantics/B5.zh-CN.md)

### C1 相同术语在不同产品中对应不同层级

[读取独立案例](cases/product-scope/C1.zh-CN.md)

### C2 新版改名，不代表旧版参数可以直接替换

[读取独立案例](cases/product-scope/C2.zh-CN.md)

### C3 正文项目用语与精确 UI 名称不必相同

[读取独立案例](cases/product-scope/C3.zh-CN.md)

### D1 同一词形分别是概念、列名和业务数据

[读取独立案例](cases/protected-content/D1.zh-CN.md)

### D2 OCR 可疑字符不能靠常见拼写补齐

[读取独立案例](cases/protected-content/D2.zh-CN.md)

### D3 占位符名称保留了，但位置对应关系被交换

[读取独立案例](cases/protected-content/D3.zh-CN.md)

### E1 PDF 抽取顺序打乱，脚注中的适用条件消失

[读取独立案例](cases/document-structure/E1.zh-CN.md)

### E2 合并表头与公式让“空白格”失去含义

[读取独立案例](cases/document-structure/E2.zh-CN.md)

### E3 图中主备角色互换，单词都正确仍然是错译

[读取独立案例](cases/document-structure/E3.zh-CN.md)

### E4 HTML 属性有些可译，有些承担程序绑定

[读取独立案例](cases/document-structure/E4.zh-CN.md)

## 方法与案例模式参考

- [MQM Core Typology](https://www.themqm.org/mqm-pillars/the-mqm-core-typology/)：术语、准确性、遗漏、设计与标记的区分。本文五类按 DBabel 的排查需要组织，并非照搬 MQM 分类。
- [技术步骤的上下文与层级](https://developers.google.com/style/procedures)、[面向翻译的技术写作](https://developers.google.com/style/translation)：A 类、B 类的步骤范围与条件表达。
- [概念定义资料 A](https://dev.mysql.com/doc/refman/8.0/en/create-database.html)、[概念定义资料 B](https://www.postgresql.org/docs/17/ddl-schemas.html)：C1 的跨产品同名概念模式。
- [空值与比较语义](https://www.postgresql.org/docs/17/functions-comparison.html)、[空值与空字符串](https://dev.mysql.com/doc/refman/8.0/en/problems-with-null.html)：B5 的概念边界与三值逻辑。
- [版本化命名资料](https://dev.mysql.com/doc/refman/8.0/en/change-master-to.html)：C2 的旧语法、新名称与弃用范围。
- [HTML 翻译边界](https://www.w3.org/International/questions/qa-translate-flag)：E4 的属性角色与保护范围。

这些公开资料支持问题模式和核查方法；正式任务仍需读取实际产品、版本与项目范围的证据。

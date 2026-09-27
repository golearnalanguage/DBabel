# 研究依据

[English](RESEARCH_BASIS.md) · [文档目录](INDEX.zh-CN.md)

这些资料说明 DBabel 的概念、范围、证据、保护内容和技术表达设计。方法依据与产品事实分开记录：文体指南不能证明某个数据库的功能或参数值。

## 技术翻译和规格信息呈现

- Jody Byrne，*Technical Translation: Usability Strategies for Translating Technical Documentation*，Springer，2006，DOI：[10.1007/1-4020-4653-7](https://link.springer.com/book/10.1007/1-4020-4653-7)。出版社简介和目录将技术翻译与可用性、技术传播联系起来。本次查阅的是公开简介和目录，没有取得全书；不将冒号、比较符号或 CPU 案例归为书中原话。
- Microsoft Style Guide 的 [Lists](https://learn.microsoft.com/en-us/style-guide/scannable-content/lists) 支持用简短、一致的列表结构帮助扫读；[Tables](https://learn.microsoft.com/en-us/style-guide/scannable-content/tables) 说明相关信息的紧凑表格呈现。这是官方写作指导，不是具体产品需求的证据。

DBabel 将这一应用命名为 `SCANNABLE_SPECIFICATION_PRESENTATION`：使用清晰的属性与值表达，同时保留对象、数量、单位、比较关系、约束强度及适用范围。B3 用合成服务器规格演示。要求保留版式时，在现有段落或单元格内改写；新增列表或表格需单独决定。以上来源于 2026-09-27 查阅，案例中的参数仍需适用产品的实际证据支持。

## 术语与本地化资料

| 资料 | 对应设计 |
|---|---|
| [ISO 704:2022](https://www.iso.org/standard/79077.html)，术语工作原则与方法 | 区分概念、名称、范围和证据 |
| [ISO 16642:2025](https://www.iso.org/standard/87351.html)，术语标记框架 | 术语资源模型与展示格式分离 |
| [ISO 30042:2019](https://www.iso.org/standard/62510.html)，TBX | 术语资源交换的后续适配方向 |
| [W3C ITS 2.0](https://www.w3.org/TR/its20/) | 可翻译性、术语和本地化质量问题分类 |
| [OASIS XLIFF 2.1](https://docs.oasis-open.org/xliff/xliff-core/v2.1/xliff-core-v2.1.html) | 文本与行内代码等非语言内容分离 |
| [NIST CSRC Glossary](https://csrc.nist.gov/glossary) | 根据来源出版物的上下文理解定义 |

当前实现使用 DBabel 自身的 JSON/CSV 项目术语表和双语单元契约。TBX、TMX、XLIFF 仍为后续适配工作，不能把参考某标准写成已经兼容该格式。

## 文档与运行时依据

内置格式探测使用 Python 标准库和有限范围检查。可选检测器或解析器属于能力后端，详见[后端登记](../plugins/FORMAT_BACKENDS.md)。识别格式、解析器可用、成功提取和完整覆盖是不同状态，需依次验证。原格式写入方案与开源候选见[实现评估](NATIVE_EXPORT_ASSESSMENT.zh-CN.md)。

厂商文档和术语在具体任务中按产品、版本和文本用途检索，不整批复制到仓库；只有打开并核对的来源才能作为对应判断的证据。

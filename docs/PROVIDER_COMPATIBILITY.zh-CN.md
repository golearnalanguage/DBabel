# API 兼容与恢复

[English](PROVIDER_COMPATIBILITY.md)

按网关实际协议选择：NewAPI 等兼容服务选择 **Chat Completions**，`/responses` 选择 **Responses**，Anthropic 原生接口选择 **Claude Messages**。支持基础地址和完整端点，不重复拼接路径；模型名按网关提供的名称填写。连接测试成功不代表整个文档流程已通过。

公司接口必须先接入公司内网或 VPN。建议先启用流式响应和 300 秒空闲超时；代理遵循公司实际网络路径，可用系统代理或直连。可信 HTTP 内网地址沿用显式授权开关，HTTPS 仍校验证书；不限制厂商或模型名单，安装包不含公司地址和密钥。

桌面配置可选择协议、流式响应、是否省略 temperature、超时（1–600 秒），并填写可选模型参数 JSON。导入的配置也支持 `max_output_tokens`。例如 `{"thinking":{"type":"disabled"}}` 仅在用户填写时发送，是否支持由网关与模型决定；此处不得填写密钥。推理系列模型默认省略 temperature；400 错误明确拒绝 temperature 或 stream 时，各做一次兼容回退，其他错误正常显示。

支持 JSON 与 SSE 的完整译文解析，包括心跳、多行 data、不同换行、用量与结束标记。思考文本、工具调用不会充当译文；响应截断、乱码、输出 token 耗尽、空闲超时、空答案不会记为完成。缓存大小有上限，流式总时限为 `max(600, timeout_seconds * 6)` 秒。

请求最多尝试三次，退避等待或 Retry-After 最长 60 秒。401、403、402 立即停止。翻译或语义批次中断后拆半，后续沿用较小批次；格式校验失败只针对具体问题重试。成功批次实时保存；续跑可调整超时、流式、代理、temperature 和模型参数，不重做已完成内容。原文、语言、端点、模型和协议身份必须一致；新参数不会重新生成已完成的译文。

## 上游代码审核

2026-10-03 参考并审核 [OpenAI SSE 解码](https://github.com/openai/openai-python/blob/main/src/openai/_streaming.py)、[OpenAI 重试处理](https://github.com/openai/openai-python/blob/main/src/openai/_base_client.py)、[NewAPI OpenAI 适配器](https://github.com/QuantumNous/new-api/blob/main/relay/channel/openai/adaptor.go)。重点是事件边界、结束标记、错误分类和渠道参数转换。DBabel 独立实现协议适配，没有复制上游代码，没有捆绑 NewAPI 服务、插件或新增网络依赖；成熟代码也不能证明所有公司渠道均兼容。

本地模拟网关测试覆盖流式响应、限流、终止错误、原生协议、拆批和参数调整后的续跑。公司 token 策略、内网超时、模型名称、扩展参数仍需在公司网络实测。

## 便携审核

Portable HTML 不依赖网络或 API 账户，浏览器本地缓存审核决定、当前位置及未完成译文/备注，并绑定会话与原始单元内容，输入不符不会恢复。清理浏览器、隐私模式或存储失败会影响缓存。**保存进度**下载包含决策和未完成编辑的恢复 JSON；**恢复进度**只允许恢复到匹配的会话。**导出 decisions.json** 仍用于本地工作台决策交换，未确认编辑只恢复到编辑框，不视为批准译文。将决策导入对应完整本地工作台后重新 QA，才能做原格式交付；原格式导出和 AI 聊天仍属于完整本地工作台。

# 每次发送前检查完整输入，共享整次写作额度

这个独立候选解决一个具体问题：章纲、正文、审校、修订和复审分别合规，并不等于整轮调用有总上限。新增入口让各角色共用同一份额度；输入太大或下一次调用会超额时，发送前停止，不裁掉设定、事实或必要前情。

## 先分清使用方式

主使用方式仍是 GPT + GitHub 插件按项目规则写小说。**GitHub 文件读取不执行 Python，本模块也不能计量或限制 ChatGPT 对话本身、Pro 订阅额度或所选模型的内部推理。** 没有实际执行器时，只能按对话协议说明资料范围与缺项，不能声称运行了自动额度检查。

已有授权执行器和已获准使用的兼容模型端点时，可以调用下方 Python 入口。本轮只用原创合成资料和 HTTPX MockTransport 验证；没有开新服务、添加凭据、部署或调用付费模型。

## 实际限制的内容

同一个 BudgetedWritingSession 在多次 run / run_from_plan / enrich_style / extract_memory 之间持续共用额度，不在失败后自动重置：

- 单次完整 HTTP JSON 请求的实际 UTF-8 字节数，包括 messages、模型、输出上限、格式参数等
- 整个 session 累计请求字节数
- 实际拥有的 OpenAI-compatible HTTP 发送尝试次数；明确“不支持 response_format”导致的那一次回退也单独计数
- 所有已发送尝试的 max_tokens 上限之和；发送前按最坏情况全额预留，短回答或报错都不自动返还

默认上限分别为单次 512 KiB、累计 2 MiB、8 次请求、累计 98,304 个输出 token 的请求上限。它们是可明确调整的工程额度，不是推荐的模型窗口、文学篇幅或人民币/美元花费。

完整“章纲→正文→审校→修订→复审”通常需要 5 次；实际是否修订依赖现有审校结果。格式回退、后续文风分析或记忆提取会继续占用同一额度。达到上限会抛出 RequestBudgetExceeded，不把未执行的复审标成通过。

## 可选实际执行入口

```python
from novel_ai.budgeted_writing import BudgetedWritingSession
from novel_ai.orchestration import RouterConfig
from novel_ai.provider import ProviderConfig
from novel_ai.request_budget import RequestBudgetLimits

# 下列变量都必须由执行器从当前已授权环境取得；这里没有提供或保存密钥。
session = BudgetedWritingSession(
    RouterConfig(
        local=ProviderConfig(writer_url, writer_model),
        reviewer=ProviderConfig(reviewer_url, reviewer_model),
    ),
    limits=RequestBudgetLimits(
        max_requests=8,
        max_request_bytes=512 * 1024,
        max_total_request_bytes=2 * 1024 * 1024,
        max_reserved_output_tokens=96 * 1024,
    ),
)

# bible、characters、plan、private_context 来自当前已核对的私有资料。
# 本模块不会替作者确认计划，也不会自动核验这些来源的新鲜度。
candidate = session.run_from_plan(
    bible=bible, plan=plan, characters=characters,
    extra_context=private_context, review=True, auto_repair=True,
)
print(session.budget_snapshot())  # 仅额度/请求摘要，不含正文、端点或凭据
# candidate 仍待作者按具体版本接受，不能因为执行成功就写入 Canon。
```

如果前一步历史/上下文预检被阻塞，调用者应先处理阻塞，不能把它的文本直接送入模型。本模块只负责请求额度，不能取代作者接受、来源版本、读者揭示或事实一致性门禁。

`session.run` 继续使用原 RoutedNovelEngine；`run_from_plan` 继续使用原 NovelEngine.run_from_plan，不另建写作流程。writer 与 reviewer 从构造时的明确配置创建，后改调用者的 ProviderConfig 不会把稿件悄悄改送到别的地址。复用一次 session 才有整轮上限；显式新建 session 就是新的额度，不能把这称作续用旧预算。

## 失败、恢复与能力范围

- 超额和无效布尔开关/篇幅目标在相关发送前拒绝；不会用字符串 "false" 开启修订
- 已开始发送的失败尝试仍保留预留额，因为无法证明服务端没有执行或计费
- 关闭 session 只阻止新发送，不取消已在途的请求，也不清空统计
- 原稿、Canon、作者确认、磁盘文件不由此模块写入；失败不会自动接受候选。执行中生成但尚未返回的候选也没有被自动存盘
- 线程中的并发请求按同一把锁原子预留；继承到 fork 子进程的预算会拒绝。活动账本禁止浅复制、深复制和序列化重建。没有多进程/多设备共享账本或持久化恢复额度
- 有界入口不接受外部 Hook、自带 reviewer 或结构化 SDK，也拒绝 LiteLLM 的不透明内部重试/回退；旧可选接口仍保留，但不能冒称受这一整轮额度覆盖
- 输入字节不是实际 tokenizer token、服务端聊天 framing 或上下文窗口。输出预留不是实际消耗，actual_tokens / actual_cost 明确为空；无金额硬上限承诺
- 这里只支持文本 system/user/assistant messages；工具调用、多模态等新格式需独立适配，不能悄悄丢字段

原 TokenCounter 的可选 tiktoken/字符估算及 clip 仍保留给旧功能；硬门禁不使用估算兜底或截断。没有下载模型或编码资源。

## 来源和候选关系

实际执行的是 [PydanticAI 小范围源码移植](../third_party/pydantic-ai-usage-limits/NOTICE.md) 的请求数/输出额度检查。核实 20,308 星、MIT，固定提交 `675d9f52b38e4dffe0c248451b5fb44595f7308c`，原源码、完整许可证和 Git blob 校验均保留。Novel 添加的是完整请求预留与现有入口接线，不把整套上游框架或定价系统说成已安装。

还核对了 openai/tiktoken 的明确编码接口（19,361 星、MIT，提交 `4e71bbe0c078468e00fefbf94b39849389f346e5`）。仅文本编码不能证明任意兼容端点的聊天 framing、上下文窗口或费用，因此本轮没有新增它的代码/依赖，也没有把比较算成新融合数量。

本独立候选从 #51 的精确提交 `bcd34013f436f58a894daba71497ee4702ca27da` 建立自己的分支 `feat/request-budget-20261001`。完整继承 #51 的 13 个改动文件且保持原字节；不覆盖其分支，不合并 main。另一份本地未发布的更完整历史来源扩展仍单独保留，没有混入本候选。

所有测试使用合成输入。工程通过不证明小说质量、真人作者身份、跨设备原件新鲜度或生产安全验收。

## 本轮工程验证

继承 #51 后，完整 Linux Python 3.11 / 3.12 回归均为 **1336 passed、1 skipped**。新增 130 项额度测试含 54 项独立复审。唯一跳过是可选 qdrant-client 未安装。全部请求使用离线 MockTransport；没有真实模型、付费调用、真人文学评估、跨设备账本或硬金额上限测试。

独立复审发现并已修复无效控制参数提前花费、调用者配置变更导致目的地漂移、预算浅复制分裂计数、缺少 reviewer 却先请求计划。最终具体远程 head 与 CI 回执以本 PR 和交付包 verification 为准，不能用旧 #51 的 CI 冒充新代码通过。

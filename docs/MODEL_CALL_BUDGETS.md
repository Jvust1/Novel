# 完整输入与多次模型调用预算

本候选接在 `fix/accepted-history-rebuild-20261002` / Draft PR #55 之上，解决此前已明确记录的两个边界：写作入口只有单次输出上限，没有完整输入门；兼容重试、结构化后端 fallback 与多模型 fallback 各自有单次上限，但没有一个共享的累计尝试预算。

当前候选不会删减必要 Canon、人物知识边界、已接受历史或当前计划来“塞进窗口”。输入超过配置额度时，在真正调用 provider 之前失败；调用方应减少非必需 Recall、调整配置或换更大上下文，而不是静默裁掉必要事实。

## 1. 两层预算

`OutputPolicy` 继续保留每个阶段的单次输出上限：

- plan: 8192
- draft: 16384
- review: 8192
- repair: 16384
- style: 4096
- memory: 8192

新增：

- `max_input_tokens = 65536`：一次实际模型调用的完整消息输入门。
- `max_attempts_per_stage = 3`：同一阶段兼容重试 / fallback 最多可见尝试次数。
- `total_output_tokens_for(stage) = tokens_for(stage) * max_attempts_per_stage`：同一阶段所有尝试共享的输出 token 预留上限。

这里的“累计”针对**同一阶段为得到同一个结果而进行的重试或 fallback**，不是把计划、正文、审校等彼此不同的工作强行合成一个总额度。

## 2. 输入计量

`TokenCounter.count_messages()` 会对完整消息列表做规范 JSON 计量，包含 role/name/content 等实际传入字段，不只数正文字符串。

`NovelEngine` 默认调用 `TokenCounter.from_tiktoken("o200k_base")`：

- 环境有 tiktoken 时使用该编码器；
- 没有 tiktoken 时使用已有的确定性字符回退；
- 无论哪种模式，都只是 Novel 配置的工程计量，不声称等于某个远端模型私有 chat template 的精确账单 token 数。

如果输入超过 `max_input_tokens`，`ModelCallBudget.claim()` 在 provider/backend 调用前抛出 `ModelBudgetExceeded`，并明确说明 required context 没有被裁剪。该失败不计为一次远端尝试，也不预留输出 token。

这与 `ContextAssembler` 的 Canon/Recall 分层预算互补：ContextAssembler 决定哪些 Recall 可以不选；最终模型调用门负责检查实际完整 messages。必要 Canon、知识边界、显式要求的已接受历史不能靠截断绕过。

## 3. 为什么失败尝试也占预算

每次真实后端尝试前，预算账本先“预留”本次 `max_tokens`。如果请求随后超时、HTTP 报错、结构化校验失败或模型 SDK 抛异常，预留不会退款。

原因：调用端无法从一个异常证明远端模型实际生成了 0 token。只有把失败尝试也计入累计上限，才能在没有 usage 元数据时仍然给出保守的最大消耗边界。

如果剩余累计额度小于原始单次 cap，下一次调用会只拿剩余额度。例如：总额 1500，第一次预留 1000，兼容重试最多只能拿 500。

## 4. 已接入的真实调用路径

### OpenAI-compatible HTTPX

`OpenAICompatibleProvider.chat(..., budget=...)` 在每次 HTTP 请求前 claim：

- 正常请求最多一次；
- 只有已验证的 `response_format` 不支持 400/422 才允许一次兼容降级；
- 第二次请求与第一次共享同一个预算，不能重新获得完整总额；
- auth、限流、服务错误、传输错误仍不会自动重试。

### Structured fallback

`FallbackStructuredExtractor` 在每个实际 adapter 调用前共享 claim。默认最多三次，保持 Guidance / Instructor / Outlines 三层候选链的兼容性。预算耗尽或尝试次数耗尽时直接停止，不会继续调用第四个或更后的隐藏后端。

### LiteLLM

没有预算对象的历史直接调用保持原有 LiteLLM `fallbacks` 行为，避免破坏外部调用者。

从 `NovelEngine` 进入时会传入共享预算；此时模型 fallback 被展开为显式顺序调用，每次 `num_retries=0`，每个模型都先从同一预算 claim。这样不会把多模型 fallback 藏在 SDK 内绕过 Novel 的累计预算。

### 自定义 provider / structured extractor

如果扩展显式声明 `budget` 参数，Novel 会把共享账本交给它。没有声明该参数的旧扩展仍可兼容，但 Novel 只允许并计量一个 engine-visible 调用；扩展内部自行实现的隐藏重试不属于已证明的预算边界，若需要累计保证应实现显式 budget 合同。

## 5. 验证的反例

本轮新增测试覆盖：

1. 完整 normalized messages 被计量；输入只差 1 token 时，在任何 provider 调用之前拒绝，调用次数为 0。
2. 预算预留不因失败退款；第一次取 10、总额只剩 5 时第二次只能取 5。
3. HTTP `response_format` 兼容重试共享总额：第一次 1000、总额 1500 时第二次实际请求 `max_tokens=500`。
4. 只允许一次尝试时，HTTP 兼容重试在第二个请求发出前被拒绝。
5. Structured fallback 总额 500、单次请求 321 时，第二后端只能拿 179；第三后端不被调用。
6. LiteLLM 在预算模式下不再把 fallback 隐藏给 SDK，实际调用顺序和每次额度都可核对。
7. 原有单次输出字节、严格 JSON、finish_reason、usage 上限及三种结构化 adapter 的测试继续通过。

当前本地 Python 3.13.5 已通过：

- token/provider/structured/model-output/routed/orchestration 相关：188 passed；
- writer output 非 Streamlit 部分：22 passed；
- `py_compile`：token_budget/output_policy/provider/structured_output/engine/routed_engine 通过。

当前容器仍未安装 Streamlit，因此真实全量测试继续由 GitHub Actions 的 Python 3.11 / 3.12 环境承担。

## 6. 明确边界

- `max_input_tokens` 是配置的工程计数门，不是远端厂商账单或模型 context window 的官方证明。
- 没有可靠 provider usage 时，累计输出使用“最大可能预留”而不是虚构实际 token 消耗，因此结果偏保守。
- 本轮不自动修改用户套餐、API 配额或模型价格逻辑；这里只控制 Novel 发出的调用边界。
- 不因预算不足自动丢 Canon、人物知识边界、已接受历史或必要计划；必须阻塞并让上层决定减少非必需 Recall、提高预算或换模型。
- 本轮没有建立跨 plan/draft/review 等不同语义阶段的统一消费金额预算；它们仍有各自明确阶段额度。

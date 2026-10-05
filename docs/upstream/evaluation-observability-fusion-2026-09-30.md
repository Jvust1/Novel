# Evaluation + Observability Upstream Fusion — 2026-09-30

这一批不再增加生成框架，而是让 Novel 能用同一套冻结样本持续比较不同模型、提示词、Recall 后端和 Agent 组合。

## Upstreams

| Project | License | Inspected revision | Novel integration |
|---|---|---|---|
| confident-ai/deepeval | Apache-2.0 | `b13093cf9c9b5468dbe7d00529e8f20e14300d55` | `DeepEvalMetricAdapter`，把 `metric.measure()` / score / reason 映射成 Novel 统一指标 |
| promptfoo/promptfoo | MIT | `e6b46046e7f454edc54b27143cb0902d929f3fa6` | `promptfoo_config()`，导出 prompts/providers/tests 配置用于跨模型回归 |
| langfuse/langfuse | MIT-core / repository-specific EE dirs | `0de9ccd64e0f9d35c1990fb6c851fa00530e7960` | `LangfuseScoreSink`，通过 Python SDK v4 `create_score()` 把 Novel 指标挂到 trace |
| vibrantlabsai/ragas | Apache-2.0 | registry retained | 继续作为 Recall/RAG 专项评估候选，不进入正文核心评测默认路径 |

## Novel 自己新增的稳定契约

- `EvaluationCase`：冻结输入、当前输出、期望输出、context、metadata。
- `MetricScore`：统一 score / threshold / passed / reason。
- `EvaluationReport`：统一 case 结果和 pass rate。
- `CallableMetricAdapter`：承接 Novel 自己的确定性质量、一致性、原创性指标。
- `DeepEvalMetricAdapter`：可选 LLM-as-a-judge / regression metric。
- `promptfoo_config`：把同一批 case 导出给 Promptfoo 做 provider/prompt matrix。
- `LangfuseScoreSink`：把回归结果和运行 trace 关联。

## 边界

外部评测框架都不决定 Novel 的“最终质量真相”。冻结样本、版本、指标阈值和人审记录仍由 Novel 自己保存；第三方只作为可替换执行后端。

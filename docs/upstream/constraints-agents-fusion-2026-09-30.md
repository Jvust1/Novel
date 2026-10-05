# Constraints + Agents Upstream Fusion — 2026-09-30

本批继续吸收千星级开源项目，补齐 Novel 的“生成约束、输出校验、多 Agent 编辑协作”。

## Upstreams

| Project | Stars snapshot | License | Inspected revision | Novel integration |
|---|---:|---|---|---|
| dottxt-ai/outlines | 15.9k | Apache-2.0 | `c52af8472c6fe8a607a733ec11b709476af77a96` | `OutlinesStructuredExtractor`，在生成阶段约束 Pydantic/JSON 结构 |
| guardrails-ai/guardrails | 7.4k | Apache-2.0 | `06d0ff2c5f9bcb493d976b76f885e37e41ce845d` | `GuardrailsReviewHook`，把校验失败映射为 Novel 的标准审校 issue |
| microsoft/agent-framework | 13.5k | MIT | `4b0e3d8e84c2beb140ef3345892908e42b48ea18` | `AgentFrameworkReviewHook`，作为微软系多 Agent 编辑工作流的首选实验入口 |

## 取舍

- 不再新增 AutoGen 适配器：上游已进入 maintenance mode，并明确建议新项目迁移到 Microsoft Agent Framework。
- Outlines 与 Instructor 并存：Instructor 侧重 schema-first API/重试，Outlines 侧重约束式生成和本地模型。
- Guardrails 不替代 Novel 已有 quality/originality/consistency gates，只作为额外可选验证层。
- Agent Framework 默认关闭；Novel core、单模型生成、现有 review path 均不受影响。

## 收益

1. 计划、审校、记忆抽取可在“生成时”就约束结构，而不是事后抢救 JSON。
2. 可把第三方 validator 的失败统一并入 ChapterReview。
3. 微软多 Agent 路线直接跟进 Agent Framework，避免把新代码押在维护模式框架上。

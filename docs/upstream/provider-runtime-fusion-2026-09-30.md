# Provider + Runtime Upstream Fusion — 2026-09-30

本批继续吸收千星级上游，但只补 Novel 现有 Provider/Router 的真实缺口。

## Upstreams

| Project | License | Inspected revision | Novel integration |
|---|---|---|---|
| BerriAI/litellm | MIT core / enterprise directory separate | `b370996b9d2fc9aaec356013a698711ee3e127cc` | `LiteLLMProvider` + `LiteLLMConfig`，支持主模型 + fallbacks，并接入 `ProviderRouter` |
| sgl-project/sglang | Apache-2.0 | `bd66ce343e4f6e2f2b75d7e820fe4d0718a8d824` | `sglang_provider_config()`，把 SGLang 的 OpenAI-compatible `/v1/chat/completions` 服务直接纳入 Novel ProviderConfig |

## 运行方式

### LiteLLM
通过环境变量即可接入现有角色路由：

- `NOVEL_LITELLM_MODELS=openai/model-a,anthropic/model-b`
- `NOVEL_LITELLM_API_KEY=...`
- `NOVEL_LITELLM_API_BASE=...`（可选）

路由优先级保持 Novel 自己控制；LiteLLM 只作为可选 gateway/fallback 层。

### SGLang
SGLang 继续作为外部推理服务，不把重型 server 依赖装进 Novel core。启动 SGLang server 后，用 `sglang_provider_config(base_url, model)` 生成标准 `ProviderConfig`，其余代码无需知道底层是 SGLang。

## 边界

- 不把 LiteLLM enterprise 目录代码复制进 Novel。
- 不把 SGLang server vendor 进仓库。
- Novel 的任务角色路由仍由 `ProviderRouter` 决定。
- API keys 仍只从运行时配置读取，不写入仓库。

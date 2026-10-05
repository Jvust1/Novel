# 1000+ Star Final Fusion — 2026-09-30

这轮用于 Novel 收尾：把 2026-09-29 已核实为 1000+ Star 的上游，从“候选/参考”推进到可测试的 Novel 适配层；不把大型框架整库塞进核心，也不改变默认生成路径。

## 本轮实际融合

| Upstream | Stars snapshot (2026-09-29) | License | Inspected commit | Novel 落点 |
|---|---:|---|---|---|
| mem0ai/mem0 | 66,303 | Apache-2.0 | `94c3fe9f238f3dbf29c9ce98643bd71eb13077cd` | `Mem0RecallBackend`，实现 Novel `RecallBackend`；写入使用 `infer=False`，保留 Novel 结构化记忆为权威 |
| stanfordnlp/dspy | 38,416 | MIT | `9c900c7de0a3cc3114c23fe8202ebe48e2206ce1` | `DSPyReviewHook` + lazy `dspy.Predict` 工厂，用于可测的二次审校/提示程序实验 |
| crewAIInc/crewAI | 59,176 | MIT | `a0d16dde6ecf205211f639d613eceef0cc42ae20` | `CrewAIReviewHook`，把已配置 Crew/Flow 作为二次编辑审校器接入 NovelEngine |
| qdrant/qdrant | 34,879 | Apache-2.0 | existing qdrant-client pin `cf747f4b6fa71ba35dfb467931f3fa65f2cdf263` | 已有 `QdrantRecallBackend` 保持 A/B gate |
| SillyTavern/SillyTavern | 33,915 | AGPL-3.0 | architecture reference only | 继续只参考 lorebook/world-info、角色状态和上下文 UX，不复制 AGPL 源码进 Novel core |

## 核心融合点

1. `NovelEngine.run(..., external_review_hooks=[...])` 增加显式二次审校入口。
2. 外部 hook 只返回标准化 issue，由现有 `merge_quality_issues` 统一决定是否进入 revise。
3. 草稿和 auto-repair 后文本都会经过同一显式 hook 链，避免“修完不复查”。
4. Mem0 只作为实验 RecallBackend，不替换 Canon/Active/Recall 默认路径。
5. DSPy/CrewAI 都是 lazy/optional；未安装依赖时 Novel core 仍可运行。
6. 所有第三方能力继续记录 upstream、commit、license；AGPL 项目不直接内嵌核心源码。

## 为什么不整库复制

Mem0、DSPy、CrewAI 都是快速迭代的大型框架。收尾阶段把整库 vendor 进 Novel 会制造重复依赖、升级负担和许可证维护成本。这里采用“稳定契约 + 可选适配器 + 来源钉住”的方式，把真正有用的能力搬进 Novel 的运行协议里，同时让核心保持可控、可回退、可 A/B。

## 发布前门槛

- `python -m compileall app.py novel_ai`
- `pytest -q`
- 真实长篇样本 A/B：Novel core vs Mem0/Qdrant recall
- 二次审校 A/B：core review vs DSPy/CrewAI hook
- 未通过冻结评测前，不把任一外部框架设为默认

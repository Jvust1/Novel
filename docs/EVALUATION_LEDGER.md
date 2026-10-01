# 2026-10-01 — 来源绑定续写候选

最终本地 Python 3.11 / 3.12 全量回归各 **1591 passed、1 skipped**（123.20s / 123.45s），新增 97 项实际入口检查，含 55 项独立反例审查。实际请求使用 HTTPX MockTransport；模型输出和作者确认均为原创合成测试数据。唯一跳过是可选 qdrant-client 未安装。

来源在各阶段或格式降级响应中变化会拒绝下一请求/候选，完整文风和 Canon 留在请求中，预算失败不退款、不重置；第二章明确接受后真实保存/读回再进入第三章。首章空历史身份歧义与人物名歧义在新入口明确拒绝，不改旧接口默认含义。两版 compileall、scoped F821、新模块完整 Ruff 和文档链接检查通过。真实长篇与文学质量未验收；公开提交 CI 另以对应 PR/归档回执为准。

# Evaluation Ledger

## 当前证据边界 2026年10月1日

下列 E-000、E-001 等条目分别记录当时的阶段，不互相覆盖。E-001 留存了历史真实运行记录，但本轮未读取新的人工评分原件，也未完成新的独立真人盲评，因此不把任何工程回归称为文学质量提升。

本轮只验证合成资料的文件完整性、抽取/摘要中断恢复、评测目录独占与人工评分不被覆盖，以及本地 Recall 的数值/状态/来源契约和实际写作上下文范围。显式历史范围内未验证来源的长篇告警被省略，省略不代表告警已检查通过。本轮新增的最终稿/复审绑定、有限输出、严格 JSON 与 Hook 失败门禁同样只有合成资料及替身测试；不把模型 pass 或工程全绿当作作者接受、原创性证明或可发布结论。当前工程入口见 [HANDOFF](HANDOFF.md) 和 `governance/project_state.json`；历史 Drive 快照清单不是当前源代码 HEAD。冻结 benchmark 用例、既有运行和待人工评分状态保持不变。

## E-ACCEPTED-HISTORY-20261001｜Accepted-history rebuild and next-chapter recovery
**Date:** 2026-10-01 UTC
**Status:** EXECUTABLE_HEAD_CI_VERIFIED

The candidate starts from PR #50 head `35208537aa1fb830a2325ec1dd8870bdf0564190`. Focused local execution on the extracted, Drive-readback source ZIP reports **77 passed** across `tests/test_gpt_story_state.py` and `tests/test_gpt_candidate_review.py`; the five newly added accepted-history/next-preflight checks all pass. `py_compile/compileall` for changed Python files passes. The executable candidate commit is `7f2b93367661b0038bab2885851fed607f047882`; GitHub Actions run 36856263295 reports **1206 passed / 1 skipped** on both Python 3.11 and 3.12, with compileall and pytest successful.

The new cases reproduce and guard: a retained old draft leaking after plan replacement; history use before real readback; rebuilding Voice/plan structure from accepted artifacts only; cross-story and stale-history fingerprints; candidate-only saves leaving accepted-history identity stable; restart/reload producing the same accepted-history identity; history-budget blocking; and CLI readback for accepted-history/next-preflight.

This local container is Python 3.13 and lacks Streamlit, so repository-wide collection is not claimed locally. The repository-wide matrix evidence instead comes from GitHub Actions run 36856263295: Python 3.11 **1206 passed / 1 skipped in 59.20s** and Python 3.12 **1206 passed / 1 skipped in 62.80s**. No real manuscript, live model, human author authentication or literary-quality judgment is part of these synthetic checks.

## E-000｜Foundation baseline
**Date:** 2026-08-19  
**Status:** NOT_YET_RUN

当前尚未建立冻结的真实小说生成 benchmark，因此任何“写得更好”“更像真人”“人物更立体”的判断都暂时只能视为设计目标，不能当成已验证结论。

### 计划固定评分维度

每个测试章节至少由人工按 1–5 分评分：

1. 情节吸引力 / 是否想继续读
2. 因果与场景推进是否自然
3. 人物动机是否可信
4. 人物声线是否有区分
5. 知识边界 / 时间线 / 设定连续性
6. 节奏与信息释放
7. 环境描写是否有功能、是否过量
8. 心理描写是否重复解释
9. AI 味 / 模板感
10. Style DNA 一致性
11. 章末拉力
12. 参考文本近似复用风险

### 最低测试组

- 都市现实 / 对话与人物关系重
- 玄幻 / 世界规则与战斗状态重
- 悬疑 / 信息边界、伏笔与误导重

### A/B 原则

每次只改变一个主要变量，例如：
- 直接扩写 vs 场景规划后写作
- 无人物知识边界 vs 有知识边界
- 单一风格提示 vs Style DNA
- 无审校 vs 局部审校

看过结果的 case 不再称为 unseen。第一轮真实结果无论好坏都必须保留。

## E-001｜novel-ab-v1 基准冻结与评测骨架
**Date:** 2026-09-14  
**Status:** RUN_EXECUTED_AWAITING_HUMAN_SCORE

### 首次真实运行（2026-09-14）

- **运行 ID：`run-20260914-153013`**（runs/ 目录，本地保留，不入库；正文按 A10 不进 GitHub）
- 模型：`qwen3-vl:4b-instruct`（本地 Ollama 0.32.14，4.4B）——首次运行用小模型验证全链路；模型绝对质量不代表系统上限，A/B 对照只看同模型下的变体差异。
- 3 用例 × 2 变体全部完成，无 `<think>` 泄漏；`run.json` 与空白评分表已生成。

### 客观观察（非质量结论，仅供人工评分参考）

1. **长度**：正文 822–1706 字，全部未达 3200–3600 字目标——4B 模型长度能力不足，但 A/B 同模型同条件，对照有效性不受影响。
2. **实体连续性抽查**：`mystery_calls` 的 A 变体漏掉 '祁明'/'老猫'，`xuanhuan_residual` 的 B 变体漏掉 '嗅灵盘'；其余关键实体均出现。样本过小，不构成变体优劣结论。
3. **本地 AI 味信号**：全部 6 篇的模板模式密度接近 0（该信号对短文本不敏感，以人工评分为准）。
4. 抽读发现疑似连续性瑕疵（如 urban_dispute B 变体中伤势描述与人物卡 '右手腕骨裂' 不符、A 变体开场即持有合同与章纲 '上门摊牌' 有出入）——留待人工评分在 continuity 维度处理。

### 评分与回填流程

人工填写 `runs/run-20260914-153013/scoring_sheet.csv`（12 维 × 1–5），然后 `python scripts/aggregate_scores.py runs/run-20260914-153013/scoring_sheet.csv --write`，把聚合结果（含 B−A delta）回填本节。**在回填前，任何关于"长期记忆层提升/未提升质量"的表述都是未验证假设（D-007 继续有效）。**

### 已冻结

`benchmarks/`（novel-ab-v1, version 1）包含三个原创用例，均带 Story Bible、人物卡（含知识边界）、章纲、本章目标和三轮前情（摘要/事实/时间线/伏笔/未回收线索）：

- `urban_dispute` 都市现实：对话与人物关系重
- `xuanhuan_residual` 玄幻：世界规则与战斗状态重
- `mystery_calls` 悬疑：信息边界、伏笔与误导重

SHA-256 已记录在 `benchmark_manifest.json`，由 `load_benchmark` 与测试强制校验；冻结用例不得修改，新用例只能新增并升级版本号。

### A/B 设计

单变量对照：`A_baseline`（v0.1：仅近章摘要）vs `B_memory`（v0.2：注入 Canon/Active/Recall 长期记忆）。同一模型、同一温度、同一章纲，唯一变量是长期记忆层。评分沿用 E-000 的 12 维度人工 1–5 分，评分表由运行器自动生成。


## E-002｜最终产品质量与商业化评测框架
**Date:** 2026-09-27  
**Status:** SPEC_DEFINED_NOT_YET_RUN

Novel 的最终评测从“单章质量”扩展为四级：

### A. 文本层
- 自然度 / AI 模板感
- 句段节奏自然波动
- 角色声线区分
- 心理与环境描写是否有功能
- 是否存在机械总结、统一抛光、套路化转场
- 参考文本长片段重合风险

### B. 故事层
- 开篇承诺
- 场景因果
- 人物选择与代价
- 看点 / 回报密度
- 章末拉力
- 前 3 章是否形成继续阅读动力
- 20 章内是否存在持续升级与兑现

### C. 长篇层
- 人物状态和知识边界连续性
- 伏笔生命周期
- 世界规则一致性
- 卷级问题升级是否合理
- 关系变化是否有累计效果
- 是否出现连续多章模板重复

### D. 商业发布层
- 番茄发布前可读性与合规人工检查
- 书名 / 简介 / 标签 / 开篇承诺的一致性
- 发布后的真实平台数据（由用户导入）
- 数据变化与剧情节点的关联

### Human-feel 验收

不把任何第三方“AI 检测器”作为唯一真值。至少组合：
1. 人工盲读评分；
2. 本地模板/均匀度/重复模式指标；
3. 角色声线与节奏差异；
4. 参考重合检查；
5. 必要时多个外部检测器仅作辅助观察。

目标是让成品在人类读者看来像经过作者真实构思和编辑的原创小说，而不是为某一个检测器做对抗优化。

### 商业目标

“爆款”不设为可保证结果。系统只优化可控变量，并在拿到真实平台数据后持续校准。任何“提升留存/追更/签约概率”的结论都必须来自同作品或冻结样例的 A/B / 前后对照，不允许凭感觉宣称有效。

## E-003｜Longform Engineering Fusion
**Date:** 2026-09-30
**Status:** IMPLEMENTED_AWAITING_FROZEN_EVAL

已工程接入人物口吻 DNA、人物行为模式重复、时间线矛盾候选、伏笔生命周期、全书强度密度，以及统一 RecallBackend 与可选 Qdrant。

下一轮冻结评测覆盖：
1. 同人物跨章稳定口吻与刻意口吻变化；
2. 重复行为模板与真实不同决策；
3. 时间倒序、合法插叙、冲突日期；
4. 正常长伏笔、遗忘伏笔、回收伏笔；
5. 连续高压、连续低压与题材允许的特殊节奏；
6. 基线 Recall、LocalSemanticRecall、Qdrant 的连续性错误、误召回、延迟和索引增长。

评测完成前，当前结论仅限于工程闭环已建立。


## E-004｜LangChain MMR continuity pilot
**Date:** 2026-09-30
**Status:** OFFLINE_ENGINEERING_PILOT_ONLY

Synthetic Chinese summaries cover a key-holder thread, a near-duplicate key thread, a separate ledger thread and irrelevant weather. The MMR port selects both relevant plot threads ahead of the duplicate. Tests verify deterministic selection, non-finite score rejection, bounded candidate memory, character/token budgets including labels, no match, zero recent count, unchanged Canon/Active, and an explicit default-off UI control.

Mocked five-stage tests exercise both NovelEngine and RoutedNovelEngine: plan → draft → continuity review → repair → re-review, asserting that selected historical facts reach every request. Streamlit AppTest exercises plan confirmation → draft → repair → re-review without network/model access. These tests validate engineering propagation, not an LLM's factual compliance or story quality. The original frozen `novel-ab-v1` inputs and first-real evidence are not changed or rerun.

Known limits: lexical bigrams miss synonyms and implications; at most 2,000 query/summary characters are scored; complete query-relevant sentence excerpts preserve matching late facts and negations when they fit; overlong sentences are omitted; similarity is not truth and does not override Canon, character knowledge, or human acceptance. Real long-form A/B, calibrated thresholds and human blind scores are not run.

## E-005｜spaCy speaker-span engineering pilot
**Date:** 2026-09-30
**Status:** SYNTHETIC_OFFLINE_ONLY

Reproduced the old false assignment of 林舟明's dialogue to 林舟. Added deterministic tests for longest-name order invariance, duplicate spans, leading/trailing speech tags, ambiguous multi-name tags, distant/unknown-actor addressees, negation/non-speaking fragments, adjacent pre-tags, newlines, escaped names, names mentioned inside dialogue, versioned/mixed baselines and actual NovelEngine voice-review consumption. Model responses are mocked and source sentences are original synthetic test data.

No real-model run, human blind evaluation, semantic-speaker accuracy study or manuscript benchmark is performed. False negatives remain possible with indirect speech, unknown aliases, complex clauses and nested quotations. Legacy baseline data is preserved but does not contribute to version-2 drift evaluation.

## E-006｜Combined same-project continuity and persistence pilot
**Date:** 2026-09-30
**Status:** SYNTHETIC_PROVIDER_MOCKED_ONLY

Two end-to-end tests combine MMR recall and distinct overlapping speaker names through both normal/routed engines, deterministic review, one repair/re-review, synthetic acceptance, memory extraction/application, metric-only voice storage, fresh character reload and subsequent recall. The same accepted-memory delta remains idempotent and preserves the unrelated character's unknown knowledge.

Additional Streamlit AppTests reproduced and then verified the fixes for missing character persistence and skipped revised-voice checks. Standard/refine-mode tests verify reference-overlap issues enter both review and re-review; unresolved overlap stays revise without starting a second repair. The initial separate combined baseline was 244 passed, 1 skipped before these extra regressions; final exact local counts are recorded in the review report.

No original novel/reference corpus or real provider call is used. The single skipped integration requires optional qdrant-client. Manual cloud-browser inspection was blocked by ERR_BLOCKED_BY_CLIENT on the local preview URL; headless AppTest coverage is not a visual-browser pass.

## E-007｜Existing workflow reconciliation checks
**Date:** 2026-09-30
**Status:** LOCAL_OFFLINE_ONLY

Reproduced edited chapter001 moving to the newest slot and changing Active/Recall membership. The in-place update port preserves001–006 order and updates only the existing row while removing same-ID duplicates. Added zero/negative budget tests.

Project-session tests cover separate characters/plans/styles/reference signatures and MMR flags, preserving unsaved A drafts through B and back, independent nested cache objects, no provider-credential caching and no on-switch file writes. A corrupt target JSON caused Streamlit to drop the unrendered chapter-goal widget; an AppTest reproduced the loss and verifies restoration after the recovery guard. Review also caught the valid empty-project-name cache edge and unsubmitted character-form carryover; regression tests cover their fixes.

No real model, remote CI or migration of previously corrupted chronology is claimed. The original combined source-port pilot remains separately preserved.

## E-008｜Canon field propagation
**Date:** 2026-09-30
**Status:** LOCAL_PROVIDER_MOCKED_ONLY

AppTests verify different world-rule and locked-fact values through stored load, editing, saving, new app session and the captured planning request. Another test confirms unsaved locked-fact edits remain with their book during switching. Only synthetic facts and a scripted provider are used; no claim is made about LLM adherence or real-story quality.

## E-LOCAL-20261001｜Author workflow and private review-candidate delivery
**Date:** 2026-10-01 UTC
**Status:** OFFLINE_ENGINEERING_VERIFIED; HUMAN_STORY_EVALUATION_PENDING

Preserved input baseline: full previous continuity/Canon/session snapshot tree `2c910626a27a3cc14393af91e6dd6aae6ee3a2b9`; baseline rerun Python 3.11: **261 passed, 1 skipped**.

Final local candidate checks:

- Linux Python **3.11.16**: full `python -m pytest -q -rs`, **413 passed, 1 skipped**
- Linux Python **3.12.14**: full `python -m pytest -q -rs`, **413 passed, 1 skipped**
- Both runtimes: `compileall` for app, package and scripts passed; `git diff --check` passed
- The single skip is the existing optional Qdrant integration test because `qdrant-client` is not installed, not an executed integration pass
- Core author-workflow tests: 94 synthetic tests covering safe explicit chapter selection/order, plan/text binding, stale review/context rejection, deterministic bundle/hash identity, symlink/path rejection, atomic no-clobber writes, interrupted persistence and race simulations
- Streamlit AppTest uses actual widgets and reruns with a mocked provider. It exercises Markdown import/save, scene-only notes and current editable seed plan into planning, three chapter saves, score import, candidate ZIP, repeated-save reuse, restart, A→B→A, malformed-target-load recovery, per-chapter overwrite consent, save failure/result identity, external draft changes and unreadable unrelated files
- Original synthetic pilot CLI created and reopened an 8-member ZIP: three original short chapters, outline, blank ten-dimension CSV, metadata, manifest and README. Every chapter SHA and ZIP CRC matched; `human_review_status=awaiting_human_review`, `publishability_verdict=null`. There are no filled human scores in the delivered sample
- Four-page editable Chinese running/limits guide was rendered and every page visually inspected

Independent code review found and the candidate fixed: unsafe inventory reads, chapter-ID normalization aliases, overwrite permission leaking to the next chapter, pre-provider-only overwrite checks, failed plan save retaining the wrong result identity, old manuscript memory writeback, invalid saved workspace types, and loss of scene-only author notes during planning.

Not run / not established: real provider/model quality, frozen unseen A/B, independent reader scoring, Windows device/UI, live platform rules or submission, and remote exact-head CI. Supported cloud-browser preview was attempted but blocked with `ERR_BLOCKED_BY_CLIENT`; no alternate route was used, so browser visual acceptance remains unverified. No public push, PR, merge or deployment was performed for this candidate. No cross-file transaction/concurrent-explicit-overwrite lock is claimed.

## E-GPT-ENTRY-20261001｜GPT-first writing, state recovery and licensed reuse
**Date:** 2026-10-01 UTC
**Status:** LOCAL_ENGINEERING_VERIFIED; AUTHOR_AND_READER_QUALITY_NOT_ESTABLISHED

This candidate preserves the previous engineering core and the plugin-written original r1 chapter while adding a GPT-readable entry, three licensed writing/review/repair prompts, nine provisional genre profiles, a licensed reader-reveal ledger adaptation and an optional executable state helper.

Actual upstream-to-entry trace:

- Complete unmodified MIT pytransitions core at `bd42b38f3627e6bca7274fb4d9af2e105f75da7c` → fixed `Machine` phases in `gpt_story_state` → explicit command CLI → interruption/stale/idempotent/32-chapter synthetic tests
- MIT op7418/Humanizer-zh and blader/humanizer selected rules at their recorded pins → GPT prewrite/editorial-review/local-repair files → three actual fact-locked local style comparisons, kept separate from the unchanged r1 chapter
- MIT chinese-novelist-skill five-column term/reveal record → private blank ledger and phase prompts → source/acceptance-aware, whitelist-only reader-known projection

Final local validation on Linux:

- Python 3.11.16 full suite: **503 passed, 1 skipped**
- Python 3.12.14 full suite: **503 passed, 1 skipped**
- The one skip is the existing optional Qdrant integration because qdrant-client is absent
- Compileall and final staged diff checks passed
- 49 focused state tests include a 32-chapter synthetic plan/accept/draft/review/memory/save/restore progression; confirmations are explicitly labeled synthetic fixtures, not user approval
- 23 separately authored adversarial review tests verify content-derived memory IDs, accepted-history preservation, stale edit fingerprints, exact plan/draft/source binding, missing-source blocks, data-only content and required-context budgets
- 18 entry/source/template/style checks verify pinned MIT license Git blob identities, links, empty templates, immutable original r1, only-declared-patch changes, and the scope of the original only/if condition
- Private local write plus actual reload smoke succeeded; remote Drive write/transaction behavior is not implemented or claimed by that helper

Review found and corrected: same-base candidate edits could overwrite newer drafts; same numeric revision could retain an old acceptance after source substitution; memory candidate contents could change under an old derived ID; accepted history could be dropped; required context could substitute a different location/body with the same ID/revision; known unavailable sources were not blocking; reader ledger projection required verifiable applied-memory ownership and default normalization. A prose comparison's only/if scope was also corrected rather than dismissed as stylistic.

The original public test chapter SHA-256 remains `b6d9e0d26c21658e1be0c9ab30117ca0ce53f7067c941fef8bad969d014c432e`; North Star and existing application code remain unchanged in this slice. Byte budgets are not the selected model's exact token counts. Source checks and legal state transitions do not authenticate author messages, prove semantic fact support, establish literary improvement, or provide Drive/multi-file/concurrent-writer transactions. Independent human reading, real long-novel quality, all-genre chapter evaluation and platform publication remain unverified.

Final freeze follow-ups: the material fingerprint now covers Canon/Active/Recall/style before and after confirmed updates; four additional regressions reject direct unapproved material changes. The public test bundle's scene-plan metadata path and dependent context digest were reconciled, with a new all-reference path/hash check. The chapter r1 bytes remain unchanged.

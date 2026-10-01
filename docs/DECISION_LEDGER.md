# Decision Ledger

## D-001｜本地优先 Web 原型
**Date:** 2026-08-19  
**Status:** ACTIVE

选择 Python + Streamlit 作为 v0.1，而不是先做复杂桌面端或前后端分离。

原因：当前最大风险是写作质量而不是 UI。先用低工程成本验证“人物驱动规划 + 长篇记忆 + Style DNA + 审校”是否真正提升章节质量；若内核成立，再决定 React/Tauri 等产品化路线。

## D-002｜Provider 中立
**Date:** 2026-08-19  
**Status:** ACTIVE

模型调用走 OpenAI-compatible adapter，不把项目绑死在单一模型或供应商。允许后续接 DeepSeek、OpenAI、本地 Ollama / LM Studio 等兼容端点。

## D-003｜文风学习采用 Style DNA，而非作者名提示词
**Date:** 2026-08-19  
**Status:** ACTIVE

代表文本先提取可解释统计特征，再可选用模型抽象高层语义文体特征；多来源按权重融合。参考正文不提交 GitHub，生成后做非可逆 shingle 哈希重合检查。

## D-004｜规划与正文分离
**Date:** 2026-08-19  
**Status:** ACTIVE

章纲先转为场景计划，再写正文。场景计划必须包含目标、阻力、选择、代价和状态变化。原因是“直接扩写大纲”容易产生事件罗列、人物被剧情拖着走和大量过渡性废话。

## D-005｜去 AI 味不是绝对禁词表
**Date:** 2026-08-19  
**Status:** ACTIVE

采用密度、重复、均匀度和编辑审校结合。像“仿佛”“微微”等词允许出现，但连续高密度时才提示，避免把文风修成另一种机械文本。

## D-006｜章节后处理：模型抽取 + 规则回写
**Date:** 2026-09-14  
**Status:** ACTIVE

章节定稿后由模型按固定 Schema 抽取摘要、新事实、人物状态/知识变化、时间线和伏笔（`MemoryExtraction`），但**回写**由本地纯函数 `memory.apply_extraction` 完成：知识边界（knows / does_not_know / false_beliefs）的一致性、事实与伏笔去重、未知人物拦截都由代码保证，不信任模型直接改人物卡。重复执行同一抽取结果幂等。

## D-007｜上下文组装三层预算制
**Date:** 2026-09-14  
**Status:** ACTIVE

`ContextAssembler` 按 A4 不变量组装 Canon（锁定事实 + story_state 事实 + 未回收线索）/ Active（开放伏笔 + 近章摘要）/ Recall（更早章节一行回顾），各层有字符预算上限，已 resolve 的伏笔不进入 Active。在拿到真实 A/B 评测结果前，不引入向量 RAG / 知识图谱。

## D-008｜多模型角色路由移植自过期 dev 分支
**Date:** 2026-09-14  
**Status:** ACTIVE

远端 `dev/multi-model-drive-backend-v0-2`（2026-08-24 停更）包含 ProviderRouter（按 TaskKind 角色回退路由）与 RoutedNovelEngine（writer/reviewer 分离），但其基线落后 main，整体合并会删除 main 的记忆/评测子系统。处理：只做 **additive 移植**（orchestration + routed_engine + 测试），补上 `extra_context` 透传；dev 分支本身保持不动。动机：A/B 评测与生产都受益于"草稿用便宜模型、审校用强模型"的角色分离；所有端点仍走 OpenAI-compatible adapter（D-002 不变）。路由配置只读运行时环境变量（`NOVEL_LOCAL_*` / `NOVEL_COLAB_*` / `NOVEL_V4_*` / `NOVEL_REVIEW_*`），凭据不落盘。

## D-010｜精修模式补"再审"，评审循环上限为一轮
**Date:** 2026-09-15  
**Status:** ACTIVE

Product Spec §4 定义精修 = "计划 → 正文 → 双审校 → 局部修订 → **再审**"，此前实现缺最后一环：修复后从未验证问题是否真正解决。补齐：repair 后自动 re-review，结果入 `ChapterResult.review_after_repair`。**循环上限设为一轮修复+复审**：复审仍不通过时不自动再次修复——自动循环容易在同一个问题上反复震荡并烧 token，此时把决定权交给作者（查看复审 JSON、手动再修或接受）。这符合 A8（局部修复优先）与"不被全自动流水线绑架"的 North Star 原则。


## D-011｜参考小说拆分为 Style DNA + Story DNA + Market DNA
**Date:** 2026-09-27  
**Status:** ACTIVE

最终产品允许用户导入多本参考小说，但不直接做“模仿某一本书”。参考输入拆分成三层派生信息：

- Style DNA：语言和叙事表现的可解释特征；
- Story DNA：剧情组织、冲突、回报、关系推进、悬念等抽象模式；
- Market DNA：目标平台、题材与读者的发布适配信息。

新小说必须重新生成 premise、人物网、世界设定和事件链。若与单一参考来源在具体表达或事件序列上过度接近，则触发原创性重构。

## D-012｜Human-feel 优先于“检测器绕过”
**Date:** 2026-09-27  
**Status:** ACTIVE

项目需要显著降低 AI 模板感，但不采用错别字、乱码、异常标点、随机噪声或针对单一检测器的对抗式策略。原因：这类策略既破坏阅读质量，也不能证明文本真正达到作者级质量。

质量判断优先级：
1. 人工盲读自然度与可发布性；
2. 人物声线、因果、节奏和长期一致性；
3. 原创性与参考重合风险；
4. 多种机器信号作为辅助。

因此项目可以持续优化“像人写的”，但不声明任何模型输出能够 100% 通过所有 AI 检测。

## D-013｜长篇健康状态回注
**Date:** 2026-09-30
**Status:** ACTIVE

每章回写后保存人物口吻、行为重复、时间线、伏笔生命周期和章节强度健康状态；后续章节由 ContextAssembler 将摘要后的 guard_context 注入生成上下文。告警用于约束与复核，不自动覆盖作者的刻意人物变化。

## D-014｜统一 RecallBackend
**Date:** 2026-09-30
**Status:** ACTIVE

LocalSemanticRecall 与 Qdrant 使用共享 RecallDocument / RecallHit / RecallBackend 契约。旧 add/search 保持兼容，新 upsert/query 供统一上层调用。Qdrant 默认关闭，需经冻结评测后才考虑改变默认路径。


## D-015｜Opt-in LangChain MMR history and continuity evidence
**Date:** 2026-09-30
**Status:** IMPLEMENTED_IN_DRAFT_BRANCH

The existing ContextAssembler clipped chronological history from the oldest summaries and the editor/repair prompts did not receive its history. Reuse the small MIT LangChain MMR selection loop, adapted to deterministic character-bigram scores, to prioritize relevant but less redundant accepted summaries. Keep the existing upstream commit pin and include the full MIT license. Do not import the heavyweight framework or silently select a semantic/vector backend.

The workbench experiment is default-off. Canon and Active stay authoritative; recalled summaries remain evidence, not character knowledge or instructions. Carry the assembled evidence through review and local repair, and keep one repair/re-review maximum. Expose source hashes and selected chapter IDs without storing manuscript text in provenance. Real long-form A/B evidence remains required before changing the default or claiming quality gains.

## D-016｜Canonical speaker spans and versioned Voice DNA
**Date:** 2026-09-30
**Status:** IMPLEMENTED_IN_LOCAL_DRAFT_BRANCH

Use a small licensed spaCy longest-span source port before matching explicit speech tags. This prevents overlapping registered character names from receiving each other's dialogue. Prefer omission to guessing on multi-name tags. Keep deterministic local operation and the existing author/review boundaries.

Tag new Voice DNA as attribution version 2. Old or mismatched attribution metrics remain stored but are excluded from new aggregate baselines; otherwise the fixed current measurements would be compared with contaminated history. Preserve numeric dimensions and the existing minimum-sample drift thresholds. No automatic data migration or quality claim is made.

## D-017｜Close the combined same-project author workflow
**Date:** 2026-09-30
**Status:** IMPLEMENTED_IN_LOCAL_COMBINED_PILOT

Combine the two bounded source ports and verify the information path through memory persistence. Fix the discovered missing characters.json write on accepted extraction, preserving locked-card rules. Align the confirmed-plan UI with the existing engines' initial and post-repair reference, voice, Story DNA and behavior checks, rather than allowing author confirmation to bypass deterministic review gates.

Retain the one-repair limit. Provider-mocked tests cannot demonstrate real-model quality. Persistence is the existing local multi-file mechanism, not a new transaction or a broad project-session migration.

## D-018｜Reuse stable history order and project-session isolation
**Date:** 2026-09-30
**Status:** IMPLEMENTED_IN_LOCAL_RECONCILIATION_PILOT

Port only the relevant stable summary methods from PR13 and adapt the project-state cache from PR16. Do not merge the old branches wholesale, because newer long-form code must remain intact. Preserve per-book unsaved session data during switches without caching provider credentials or automatically writing draft files. A failed target load retains a recoverable snapshot, including widget-bound values.

Do not automatically repair previously reordered history or claim session caching is persistent autosave. Existing folder naming and multi-file storage remain unchanged.

## D-019｜Preserve separate locked facts at the UI boundary
**Date:** 2026-09-30
**Status:** IMPLEMENTED_IN_LOCAL_CANON_PILOT

Port the separate locked-facts editor and current_bible mapping from PR16. Both world_rules and locked_facts retain their stored meanings; the workbench must not replace one list with the other merely because its earlier UI had a combined label. Preserve existing values, including duplicates, and do not auto-migrate story state.


## D-020｜Explicit author workflow and revision-bound review
**Date:** 2026-10-01
**Status:** IMPLEMENTED_IN_LOCAL_CANDIDATE

Reuse LangChain's MIT Markdown heading stack/fence source at the existing pin, adapting it to preserve individual authored nodes rather than lossy retrieval chunks. Keep Markdown notes as notes; require author/model completion of scene causality. Selected chapter and ancestor context enter the existing planning/drafting/review path, with no new provider dependency.

Build review corpora from explicit, safe, author-ordered saved chapter IDs. Version the corpus fingerprint to include project/stage/genre/audience/review assumptions as well as titles/text. Preserve old score files, but reject stale bindings rather than relabeling them. Human scores remain human records; a local ZIP is a review candidate with no automatic publishability verdict. Use atomic no-clobber/content-addressed exports, preserve prior result identity on failed persistence, and check exact saved chapter revision before memory extraction. Multi-file transactional saves remain outside this slice.


## D-021｜GPT repository entry and genre-derived voice
**Date:** 2026-10-01
**Status:** IMPLEMENTED_IN_DRAFT_ENTRY_BRANCH

Follow the author's clarified usage: GPT reads repository instructions through the GitHub plugin and writes in conversation; existing local tools are optional. File access does not imply Python execution, persistent private storage, or autonomous approval. Keep private actual novels and state in authorized private storage. The original public demonstration is explicitly bounded and does not establish standing publication permission.

Derive a Style Profile from the novel's primary genre, optional secondary genre, readers and scene needs. Reuse pinned MIT source guidance on voice calibration, context-sensitive style patterns and meaning-preserving local edits; add Novel's knowledge/timeline/item/foreshadowing locks. Preserve working prose and all existing software. Neither a fixed cold/colloquial voice nor detector-evasion scoring becomes a global goal. Original North Star remains unchanged.


## 2026-10-01 — Shared final-text evidence and bounded model output

Consolidate the existing post-plan writer path instead of adding another orchestrator. Bind current reports to exact text/plan/stage; preserve initial evidence and explicit author acceptance. Use existing HTTPX streaming, Python JSON and Pydantic runtime validation; reject malformed/incomplete output rather than adopting permissive partial-JSON repair. Optional backends stay opt-in and their stop/transport/cumulative-budget limits stay explicit. See [FINAL_OUTPUT_GATES.md](FINAL_OUTPUT_GATES.md).

## D-018｜下一章连续性只从实际读回的已接受历史重建
**Date:** 2026-10-01  
**Status:** IMPLEMENTED_IN_CANDIDATE_BRANCH

继续创作时，不把会话缓存、未接受候选或“文件较新”本身视为历史事实。revision>0 的历史重建必须先有实际 `load_state` 读回；来源只取追加保存的 `accepted_chapters`，并用故事身份、基础连续性摘要与每章计划/正文来源指纹生成稳定 `accepted_history_sha256`。整个 JSON 文件 SHA 仅作为本次读回证据，不进入历史指纹，因此保存当前未接受候选不会虚假制造“已接受历史变化”。

下一章预检可把最近已接受的计划/正文作为完整、可预算省略的 Recall 来源，并附加不可静默删掉的接受历史派生区。改计划后仍保留的旧 draft 只有重新绑定到当前 `plan_revision` 才能进入当前提示。任何作者接受仍由既有确认协议完成；该门禁不认证人、不自动接受稿件、不替代文学审读。

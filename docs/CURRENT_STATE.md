# Current State

## 2026-09-30（OpenWrite 大规模纳入 + 最新 main 对齐）

- OpenWrite 系已纳入工作分支：Open-Write/Open-Write 94 份、LiPu-jpg/Openwrite 207 份、travsteward/openwriter 465 份，合计 **766 份固定上游源码**，许可证与 commit provenance 保留。
- OpenWriter 另以 `third_party/openwrite/openwriter-full` 子模块固定到 `142002677685298d45569ac132af11e7ed8e70e2`，用于保留完整上游；AGPL 的 `ilrein/openwrite` 仍仅作架构参考，不混入 Novel 核心源码。
- 主线已有 prose quality gate 保留不动；OpenWrite 派生的磁盘/字节/哈希式完成校验改为独立 `novel_ai/completion_gate.py`，避免覆盖现有质量分析。
- `NovelEngine` / `RoutedNovelEngine` 产出将携带 `completion_gate_report`；冻结 benchmark 同步记录 completion gate，模型自报完成不能替代确定性检查。
- 本轮按最新 `main` 的长篇工程融合成果重建合并树，保留 Voice DNA、Story DNA、RecallBackend、Qdrant、长篇健康、原创性、层级大纲与市场发布能力。
- 工作分支：`feat/openwrite-mass-import-20260929`；PR #26 保持 Draft；`main` 未被本轮直接写入。
- PR #26 已与最新 main 对齐：mergeable=true、behind=0。最新 CI run `36683805241` 的 test job `109784953898` 为 `steps=[]` 且日志 blob 不存在；workflow 使用正常的 `ubuntu-latest`，因此记录为 `INFRA_NOT_STARTED`，不是代码测试失败。

# 2026-09-30 — 长篇小说工程融合分支

本轮在 `feat/longform-engineering-fusion-20260930` 直接收口此前分散在多个功能分支的成熟实现，并以 `feat/vendor-book-to-skill-20260930` 为最新基线，未直接修改 `main`。

## 已进入核心长篇流程

- **人物口吻 DNA**：按人物提取对白句长、问句/感叹/省略、短句比例、称谓密度、语气词等非原文特征，形成跨章基线；漂移进入 review。
- **人物行为模式重复**：按 Story DNA 的目标→阻力→选择→代价→状态变化比较历史章；高相似模式在写正文前进入 `draft_context`。
- **时间线矛盾检查**：从累计 `story_state.timeline` 检查时间回退与同一事件冲突时间候选。
- **伏笔生命周期**：统计 planted/touched/resolved、悬置章数、长期未触碰和平均回收寿命。
- **全书高潮/低谷密度**：从 Story DNA 的场景结构与 tension curve 估算章节强度，检测连续高压透支与连续低压失速。
- 上述健康状态保存到 `memory/longform_health.json`；`ContextAssembler` 会把 `guard_context` 重新注入后续章节，因此不是只做仪表盘展示。

## 直接搬运并融合的独立能力

从已有分支搬入并保留测试/CLI：
- `originality.py`：四层原创性 Gate（shingle / fuzzy / embedding / event sequence）。
- `outline.py`：series→volume→arc→chapter→scene 层级大纲。
- `market_eval.py`：番茄前三章/前 20 章市场评测数据结构与评分聚合。
- `release_pack.py`：发布包结构。
- `recall.py + qdrant_recall.py`：统一 Recall 协议与可选本地 Qdrant adapter。

## Recall 融合

原有 `LocalSemanticRecall` 与新 Qdrant 分支曾使用两套 RecallHit 结构。本轮统一到共享 `RecallDocument / RecallHit / RecallBackend`：
- LocalSemanticRecall 同时支持旧 `add/search` 与新 `upsert/query`。
- Qdrant 与本地 semantic recall 可以由同一上层接口 A/B。
- Qdrant 仍默认关闭，不替代 Canon/Active/Recall；必须先通过冻结评测。

## 尚未声称验证

这些能力已经工程接入，但“提升长篇质量”的效果仍需冻结样例 + 人工评审/A-B 验证。特别是时间线启发式、口吻漂移阈值和高潮密度阈值都需要按题材校准。


## 2026-09-30 — character voice / behavior / timeline / foreshadow / tension engineering

- Added per-character Voice DNA from attributed dialogue: average line length, short/long-line ratio, question/exclamation/ellipsis habits, pronoun density and ending particles. Raw dialogue is not stored in Voice DNA.
- Voice DNA is persisted per accepted chapter; long-term baselines detect character-voice drift. Medium/high drift is merged into Review/Repair.
- Added character behavior-pattern repetition guard from Story DNA beats (objective → opposition → choice → cost → state change), scoped to the same POV character.
- Timeline consistency checks detect comparable time reversals and the same event assigned conflicting structured time hints.
- Foreshadowing now retains lifecycle history. Resolved clues cannot silently regress to planted/advanced; attempted regressions are recorded as lifecycle warnings.
- Added foreshadow lifecycle statistics: status counts, resolved ratio, average resolution lifetime, overdue and stagnant unresolved clues.
- Added whole-book climax/low-density analysis with recent-window density and consecutive high/low streak warnings.
- Long-form health is persisted at `memory/longform_health.json` and its bounded guard context automatically enters the next chapter's ContextAssembler.
- Streamlit exposes all five long-form engineering panels and highlights timeline contradictions / overdue foreshadowing / tension-density warnings.

## 2026-09-30 — long-form Story DNA analytics dashboard

- Added pinned scikit-learn, River, Plotly and UMAP submodules.
- Accepted chapters now persist numeric chapter analytics alongside Story DNA.
- Added whole-book trope frequency statistics: tension curves, structural patterns and repeated end hooks.
- Added Story DNA clustering: scikit-learn TF-IDF + KMeans when available, deterministic event-similarity connected-components fallback otherwise.
- Added optional UMAP 2D projection for visually locating repeated plot-pattern neighborhoods.
- Added chapter-level rhythm/style drift monitoring. River ADWIN is used when available; otherwise a rolling 2.5σ fallback is used.
- Streamlit exposes the whole-book Story DNA analytics and drift panel directly from persisted project state.

## 2026-09-30 — persistent Story DNA and cross-chapter pattern guard

- Story DNA is now durable project state under `memory/story_dna/<chapter>.json` and can be reloaded across sessions.
- Before drafting a new chapter, Novel compares the approved plan's event sequence and structural pattern against historical Story DNA.
- Similarity weighting: event-sequence 78% + structural/tension features 22%; medium/high matches produce explicit review issues.
- When a match crosses the threshold, a causal-diversification constraint is injected before drafting: change character choices, resistance source, causal chain, cost, state change or information-release order; surface synonym swapping is explicitly discouraged.
- The same Story DNA guard is active in both NovelEngine and RoutedNovelEngine.
- Streamlit shows the Story DNA history and the current chapter's cross-chapter similarity report.
- Accepted chapters persist their Story DNA during memory writeback, alongside story_state, summaries and Story Graph.

## 2026-09-30 — Story DNA and Chinese structure fusion

- Pinned chinese-novelist-skill, OpenSPG/KAG and PaddleNLP.
- Added deterministic Story DNA derived from the approved chapter plan: objective/opposition/choice/cost/state-change/event sequence/hook structure.
- Added workflow phase guards for planning and draft stages, absorbing the useful multi-phase workflow idea without replacing Novel's own engine.
- Added explicit opt-in PaddleNLP UIE adapter for人物/地点/事件/目标/阻力/选择/代价/伏笔 extraction. It is never auto-initialized because model downloads are heavy.
- Added neutral Story Graph → KAG record export. Novel keeps JSON as its canonical graph format and can feed KAG only when an experiment explicitly enables it.
- Workspace now exposes Story DNA and structure-backend availability.

## 2026-09-30 — orchestration and optimization experiment layer

- Pinned Mem0, LlamaIndex, LangChain, Haystack, Chroma and DSPy as reviewed submodules.
- Added `novel_ai/experimental_backends.py`: one capability matrix and explicit chooser for memory/orchestration/vector-store/prompt-optimization experiments.
- Heavy frameworks remain opt-in. The selector only chooses from a caller-provided preference list and falls back to `novel-core` when none are available.
- This prevents framework sprawl from leaking into the deterministic core and makes future A/B experiments reproducible.

## 2026-09-30 — recall and evaluation backend fusion

- Pinned GraphRAG, LightRAG, Graphiti, DeepEval, Ragas, sentence-transformers, FAISS and HanLP.
- Semantic backend selection now supports FlagEmbedding → sentence-transformers → text2vec → char n-gram fallback.
- Added LocalSemanticRecall: FAISS accelerates local vector recall when installed; otherwise the same interface falls back to in-memory cosine search.
- Added capability matrix for FAISS / Qdrant / GraphRAG / LightRAG / Graphiti. Heavy graph/RAG systems remain behind the existing A/B gate.
- Added ReleaseQualitySnapshot combining prose quality, reference-similarity protection and cross-chapter near-duplicate checks.
- DeepEval and Ragas are explicit optional evaluator backends and are not invoked without provider/model configuration.
- HanLP is surfaced without automatic model downloads.

## 2026-09-30 — long-form graph and self-repetition fusion

- Added pinned datasketch, NetworkX and qdrant-client submodules.
- Every generated chapter can now be screened against prior local chapters; datasketch MinHash is used when installed, otherwise Novel falls back to its fuzzy similarity layer.
- Post-chapter memory writeback now also emits a portable `memory/story_graph.json` containing characters, relationships, timeline events and foreshadowing nodes.
- NetworkX is optional and only validates/deduplicates the graph; the persisted format stays plain JSON.
- Added an opt-in QdrantRecallStore adapter. It does not replace Canon/Active/Recall unless a future frozen A/B test proves a gain.

## 2026-09-30 — high-fidelity reference and semantic fusion

- Pinned MarkItDown, Docling, text2vec, FlagEmbedding, RapidFuzz and DeepKE as reviewed upstream submodules.
- Reference ingestion now prefers Docling, then MarkItDown, then the lightweight python-docx/pypdf fallback. HTML/RTF/EPUB become available when an advanced backend is installed.
- Reference Pack records which extraction backend produced each source profile.
- Semantic layer can explicitly select the strongest installed backend: FlagEmbedding → text2vec → dependency-free char n-gram.
- RapidFuzz is already consumed by the reference-similarity protection layer.
- DeepKE is registered as an opt-in Story DNA structure extractor candidate; it is not forced into the default lightweight runtime.

## 2026-09-30 — reference similarity + book-to-skill runtime fusion

- Added `novel_ai/reference_similarity.py`: non-reversible shingle overlap is the default protection; RapidFuzz/embedding/event-sequence layers are optional runtime inputs.
- NovelEngine and RoutedNovelEngine now accept Reference Pack hash signatures and merge similarity findings into the same review/repair gate as prose-quality findings.
- Streamlit workspace displays the reference-similarity protection report alongside the prose-quality and heuristic style reports.
- Added `novel_ai/book_skill_adapter.py`: Novel can invoke the pinned `vendor/book-to-skill` converter against local user documents with project-local output.
- The adapter does not copy source books into GitHub; reference documents stay local.

## 2026-09-30 — deep prose-quality fusion

- Added `novel_ai/quality_gate.py`: dependency-free core plus optional OpenCC / pkuseg / jieba / LexicalRichness / pycorrector / spaCy capability detection.
- NovelEngine now runs deterministic quality analysis immediately after drafting. Medium/high deterministic findings are merged into `ChapterReview` and can trigger the existing local repair path; low findings remain advisory.
- RoutedNovelEngine receives the same quality gate so multi-model writer/reviewer routing no longer bypasses local quality checks.
- Added optional NLP dependencies to `requirements-extras/nlp.txt`; default install remains lightweight and functional without them.
- pycorrector output is never blindly applied: names, dialogue, dialect and intentional colloquial language require review.
- The gate optimizes naturalness, correctness, variation and originality signals; it is not a detector-evasion score.

## 2026-09-30 — 1000+ star NLP integrations

- Added four pinned 1000+ star upstream projects as Git submodules: spaCy (33k+), pycorrector (6.5k+), texthero (2.9k+), OpenCC (10k+), star counts checked on 2026-09-30.
- Primary Novel goal: improve Chinese text quality, normalization, structural analysis, lexical/phrase variation diagnostics, and post-generation repair inputs.
- These integrations support writing quality/originality evaluation; they are not detector-evasion mechanisms.

## 2026-09-30 — style-quality toolset expanded

- Added pinned submodules for `LSYS/LexicalRichness`, `textstat/textstat`, `amperser/proselint`, and `lancopku/pkuseg-python`.
- Purpose: diagnose lexical repetition, sentence/readability patterns, prose issues, and Chinese tokenization quality so Novel can improve originality and naturalness through measurable writing-quality signals.
- These tools are not used to target or bypass any specific AI detector; detector scores are not a release gate.
- All four upstream licenses were checked before inclusion (MIT / BSD-3-Clause).

## 2026-09-30 — book-to-skill integrated

- Added `virgiliojr94/book-to-skill` as pinned submodule `vendor/book-to-skill` at upstream commit `c108d25b0cb58e1bdc361f3de02ed9f37075152f`.
- MIT license confirmed upstream; the upstream tree retains its original `LICENSE.md` and copyright notice.
- Novel use: convert user-provided reference books/documents into structured on-demand Agent Skills before/alongside Reference Pack and Story DNA extraction.
- Raw reference novels remain outside GitHub; only tooling is integrated.

# Current State

## 2026-09-28（成果同步）

- GitHub `main` 的开源生态集成提交 `a84917cc6d637ccade3da4d721828c6613bfc92b` 已通过 CI workflow #74。
- Drive 的 `04_Snapshots` 新增并验证 `Novel_最新成果快照_2026-09-28`，记录最终目标、本轮 38 个上游项目集成、实际落地代码、已有核心能力和下一步。
- Drive 根目录原有 `Novel-Windows-完整交付-20260925.zip` 保留，不重复上传旧包。
- `governance/artifact_manifest.json` 已登记 Drive 文件 ID、路径、内容 SHA-256、来源 commit 和状态。
- 当前 `pending_sync` 为空。


## 2026-09-27（开源生态集成第一轮）

围绕最终目标（多本参考小说 → Style DNA + Story DNA → 原创长篇 → 人味/原创性/番茄发布评测）完成第一轮开源能力纳入。

### 本轮落地

- 新增 `governance/open_source_registry.json`：首批 **38 个** GitHub 上游项目按许可证、优先级、集成模式和用途登记。
- 新增 `docs/OPEN_SOURCE_INTEGRATION.md`：定义 direct-optional / adapter / research-port / experiment-candidate / external-runtime / architecture-reference-only 六种纳入方式，禁止无脑 vendor 整库。
- 新增 `novel_ai/integrations.py`：运行时开源能力注册表与可选依赖探测。
- 新增 `novel_ai/reference_pack.py`：可从多份 TXT/MD/DOCX/PDF 构建 Reference Pack；仅保存派生 Style Fingerprint、provenance 与不可逆 shingle 签名，不保存参考正文。
- 新增 `novel_ai/semantic.py`：内置中文字符 n-gram 相似度，并提供 text2vec / FlagEmbedding 懒加载适配器，为原创性检查和 Recall 做准备。
- 新增 `scripts/build_reference_pack.py` 与 `scripts/check_integrations.py`。
- 新增 `requirements-extras/`：NLP、文档解析、Memory/RAG、评测、Provider 五组可选依赖，默认安装保持轻量。
- 新增 3 组测试：integration registry、Reference Pack、semantic similarity。

### 首批重点上游

- 长篇故事：DOC / DOC StoryGen v2 / Re3。
- 中文与语义：HanLP / jieba / text2vec / FlagEmbedding / sentence-transformers / RapidFuzz。
- 文档导入：Docling / MarkItDown / Unstructured。
- 长篇记忆实验：GraphRAG / LightRAG / HippoRAG / Graphiti / Mem0。
- 向量存储：Qdrant / Chroma。
- 模型运行/路由：LiteLLM / Ollama / vLLM。
- 评测：DeepEval / Ragas / Promptfoo / Langfuse / story-evaluation-llm / OpenAI Evals。
- 产品/上下文参考：SillyTavern、AI-Novel-Writing-Assistant（只做架构参考，受许可证策略约束）。

### 许可证策略

- MIT / Apache-2.0：可以依赖、适配或在保留 notice 的前提下移植必要实现。
- AGPL-3.0：默认外部运行或架构参考，不把源码直接并入 Novel。
- 未检测到许可证：只做架构参考，不复制代码。

### 仍需继续

本轮主要完成“生态接入口 + Reference Pack 基础”。下一轮优先：
1. Story DNA schema 与事件/套路抽取；
2. Docling/MarkItDown 高级 reader；
3. shingle + fuzzy + embedding + event-sequence 四层原创性 Gate；
4. DOC 风格层级大纲扩展；
5. Graph/RAG Recall A/B adapter；
6. 番茄前三章/前 20 章商业可读性 benchmark。


## 2026-09-15（第五轮）

精修模式补"再审"（D-010）。

- `ChapterResult` 新增 `review_after_repair` 与 `final_text` 属性；`run()` 与工作台两步流的精修路径都在 repair 后自动 re-review。
- UI 新增"精修复审"展示（verdict 着色；仍不通过时默认展开），复审不通过不自动二轮修复，交作者决定。
- 记忆抽取入口与正文展示统一走 `final_text`。
- 测试 43 项全过（新增：revise→修复→复审的完整调用序列断言；pass 时不触发修复与复审）。

## 2026-09-15（第四轮）

实现 Product Spec 的"锁定人物"机制。

### 本轮内容

- `Character.locked: bool = False`：作者可锁定已定稿的人物卡。
- 回写层：锁定人物的抽取更新不应用，记入 `unapplied_updates`（reason="人物已锁定，回写跳过"）；解锁后恢复正常回写。
- 顺带修复一个幂等性缺口：`unapplied_updates`（未知人物/锁定跳过记录）此前会跨重复运行累积，现按 (chapter_id, name, reason) 三元组去重，符合 D-006 的幂等声明。
- 工作台人物页新增锁定多选与"应用锁定"（同时落盘）。
- 测试 41 项全过（新增锁定跳过、解锁恢复两条）。
- 说明：story_state 的 facts 本身是只增不删的（append-only），无需额外锁；"锁定段落"属正文编辑器范畴，延后。

## 2026-09-15（第三轮）

基线对齐检查（PROJECT_NORTH_STAR / PRODUCT_SPEC）后补上工作台的计划确认流程。

### 发现与修复

- **缺口**：North Star 第 7 条与 Product Spec UX 原则都要求"AI 先给结构化建议，用户可编辑，再生成正文"，但 write_tab 是"生成本章"一键到底，场景计划从未给用户确认机会。
- **修复**：写作流程改为默认两步——① 生成场景计划 → 计划以可编辑 JSON 呈现（改目标、阻力、选择、代价、知识边界）→ ② 按确认后的计划写正文（计划与正文共用同一份组装上下文，保证一致性）；保留"一步生成"作为快速路径。② 在没有确认计划时禁用。
- 测试 39 项全过（新增 AppTest 门控测试：无计划时 ② 禁用、编辑器不出现；注入计划后启用且内容正确）。

## 2026-09-15（第二轮）

Review → Repair 闭环真实验证 + 一个真实环境缺陷修复。测试 38 项全过。

### 本轮内容

- **系统代理劫持本地端点（已修复）**：httpx ≥0.28 会读取 Windows 注册表系统代理；本机代理（127.0.0.1:10809）拒绝转发 loopback 目标，对本地 Ollama 的调用全部变成空体 503（curl 不读注册表所以对照正常；昨天 benchmark 成功是因为当时系统代理未开）。修复：`provider.is_loopback_url` 检测 loopback 端点并对其实例化 `httpx.Client(trust_env=False)`；远程端点保持 trust_env（云端 API 仍可走用户代理）。回归测试 3 项（loopback 判定、本地禁代理、远程保留代理）。
- **Review → Repair 真实验证**（urban_dispute B 变体 + 真实 plan，qwen3-vl:4b）：审校返回合法 JSON；verdict=pass 时修复稿与原稿相似度 98.92%——局部修复纪律在"通过"场景下不重写整章，行为正确。
- **观察（4B 审校者过宽）**：该章存在人工可辨的连续性瑕疵（E-001 已记录的伤势描述不符），4B 审校却给 pass 零问题——审校角色需要更强模型，正好验证了 D-008 角色路由（REVIEW 走独立端点）的架构价值；待有第二个端点后在 UI/评测中启用。
- 至此流水线五环节（Context → Plan → Draft → Review → Memory Update）全部经过真实模型执行验证。

## 2026-09-15

## 2026-09-15

工作台状态回载 + 评分辅助工具。测试 35 项全过（新增 Streamlit `AppTest` 应用级执行测试）。

### 本轮新增

- **工作台状态回载（可用性修复）**：app.py 新增 `seed_project_state`——按当前项目从 `memory/story_bible.json`、`outline.json`、`characters.json`、`styles/*.json` 回载设定、人物、Style DNA 与参考签名；此前重启应用虽已落盘但从不回载。策略是非破坏的：只回载已保存的数据，未保存项目保留会话现状。
- **应用级测试**：`tests/test_app.py` 用 `streamlit.testing.v1.AppTest` 真正执行 app.py（此前的 health 冒烟只验证服务器不执行脚本）——覆盖启动无异常与回载正确性。
- **评分包渲染**：`novel_ai/eval.py:render_scoring_pack` + `scripts/render_scoring_pack.py`——从 run 目录生成 `scoring_pack.md`（每用例目标/要求 + A/B 双变体全文 + 12 维锚点表），`run-20260914-153013` 已生成，供人工评分时对照。
- Ollama 服务进程曾退出（机器重启）；qwen2.5:7b 下载已按用户要求取消，第二轮评测搁置，待评分或新端点。

### 记忆回写环节真实模型验证（2026-09-15，未入库的本地验证）

用本地 qwen3-vl:4b 对 `run-20260914-153013/urban_dispute__B_memory.txt` 完整跑通 `extract_memory → apply_extraction`：

- 抽取结果符合 Schema；三个角色更新全部命中人物卡姓名（`unapplied_updates` 为空）。
- 回写正确：knows 追加、`recent_change` 带 `[004B]` 章节戳、status 合并无丢失。
- **发现抽取器的一个真实缺陷模式**：模型把疑似读者视角信息（周凯藏钥匙）写进了陈桂香的 `knowledge_gained`——"人物知道 vs 读者知道"的区分对 4B 模型不可靠。改进方向（未实施）：抽取协议中加入"逐条知识归属检查"示例，或在审校协议中增加知识来源复核项；待人工评分确认该问题权重后再动。
- 验证时 story_state 从空开始（未带前情伏笔），故模型新建了伏笔条目而非推进已有 `zhou-key`——正式流程会传入累积 state，此为验证设置差异，非代码缺陷。

## 2026-09-14（第四轮）

回收过期 dev 分支的多模型路由能力（D-008）。

### 盘点结论（只读）

远端 `dev/multi-model-drive-backend-v0-2` 停在 2026-08-24，基线远落后 main；整体合并会删除 main 的记忆/评测子系统（diff 约 -2100 行）。其有价值部分：ProviderRouter（TaskKind 角色回退路由：draft/plan/review/memory/benchmark）、RoutedNovelEngine（writer/reviewer 分离）、离线路由测试。分支保留原样，未动。

### 本轮新增（additive 移植）

- `novel_ai/orchestration.py`：原样移植（仅依赖 provider.py，无冲突）。
- `novel_ai/routed_engine.py`：移植并适配 main 的 `extra_context` 参数透传。
- 测试 +5（含 writer/reviewer 角色分离与 reviewer 缺失回退），共 32 项全过。
- 未接线：app.py 与 eval 尚未暴露路由模式；待真实端点出现后再决定 UI/评测入口（避免无端点的死配置）。
- dev 分支记录的 Ollama 前置问题（qwen3:4b，`could not locate ollama app`，安装/PATH 问题）仍待用户本机解决。

## 2026-09-14（第三轮）

CI 修复 + 评测闭环补全 + 参考文本格式扩展。测试 27 项全部通过（含 bare `pytest`）。

### 本轮内容

- **CI 修复（blocking）**：main 上 run 34797893235 失败——workflow 用 bare `pytest`，不把仓库根加入 `sys.path`。新增 `pyproject.toml`（`[tool.pytest.ini_options] pythonpath=["."]`）；修复已在 PR #4 的 CI run 34828564029 上验证通过（经授权合并后 main CI 恢复绿色）。
- `scripts/aggregate_scores.py`：评分表聚合 CLI——读取填好的 `scoring_sheet.csv`，按 run.json 的 case/variant 网格检查覆盖缺口（缺哪些维度、哪些组整组未评），输出聚合 JSON（含 B−A delta），`--write` 落盘 `scores_summary.json` 供回填 ledger。
- `novel_ai/reading.py`：参考文本导入扩展到 DOCX（python-docx）与 PDF（pypdf），懒加载依赖；app.py Style Lab 上传器已支持四种格式。
- `project_state.json`：repository 更正为 `Jvust2/Novel`（远端实际地址）。

## 2026-09-14（第二轮）

v0.2 评测骨架：冻结基准 novel-ab-v1 + A/B 运行器（E-001，状态 PENDING_RUN）。

### 本轮新增

- `benchmarks/`：三个原创冻结用例（urban_dispute / xuanhuan_residual / mystery_calls），各含 Bible、人物卡（知识边界）、章纲、目标与三轮前情；`benchmark_manifest.json` 记录 SHA-256，加载与测试强制校验，改动即报错。
- `novel_ai/eval.py`：12 维评分 rubric（E-000 口径）、变体定义（A_baseline / B_memory 单变量对照）、`run_case` / `run_benchmark`（结果写入不可变 `runs/<run_id>/`，gitignore）、评分表生成 / 读取 / 聚合（含 B−A delta）。
- `scripts/run_benchmark.py`：CLI；密钥只从 `NOVEL_BASE_URL / NOVEL_MODEL / NOVEL_API_KEY` 环境变量读取，不落盘。
- 测试增至 19 项，全部通过（含冻结哈希防篡改、变体唯一差异、评分表 roundtrip）。

### 阻塞点

真实 A/B 运行需要模型端点。运行命令与评分流程见 `benchmarks/README.md`。

## 2026-09-14

v0.2：补齐长篇记忆内核（A2 的 Memory Update 环节 + A4 的三层记忆）。

### 本轮新增

- `novel_ai/models.py`：`MemoryExtraction` / `CharacterMemoryUpdate` / `TimelineEvent` / `ForeshadowItem` Schema。
- `novel_ai/prompts.py`：章节后记忆抽取协议；plan/draft 支持 `extra_context` 注入长期记忆。
- `novel_ai/memory.py`：`apply_extraction` 纯函数回写——知识边界一致性（获得知识移出 does_not_know、澄清误解移出 false_beliefs）、事实/线索/伏笔去重、幂等、未知人物拦截进 `unapplied_updates`。
- `novel_ai/context.py`：`ContextAssembler` 按预算组装 Canon（锁定事实+未回收线索）/ Active（开放伏笔+近章摘要）/ Recall（更早章节一行回顾），resolved 伏笔不进入 Active。
- `novel_ai/storage.py`：`save_extraction` / `load_story_state` / `save_story_state` / `all_chapter_summaries`。
- `novel_ai/engine.py`：`extract_memory()`；plan/draft/run 透传 `extra_context`。
- `app.py`：生成时自动组装三层上下文；新增"抽取本章记忆并回写"按钮与 story_state 查看器。
- 测试 12 项全部通过（memory 回写幂等/知识边界/伏笔状态推进；context 分层与预算）。

### 设计要点

- 回写逻辑全部在代码侧，模型只负责抽取（D-006）；模型输出不直接改人物卡。
- 仍不引入向量 RAG / 知识图谱，等真实 A/B 评测结果（D-007）。

## 2026-08-19

Novel 已从空仓库初始化为可运行的 v0.1 本地 Web 原型。

### 已完成

- Streamlit 本地写作工作台。
- OpenAI-compatible 模型适配层；运行时输入密钥，不写入项目文件。
- Story Bible / 总纲 / 章纲输入。
- 动态人物卡：目标、秘密、知识边界、关系与状态字段。
- 章纲 → 场景计划 → 正文 → 审校 → 可选局部修订。
- 本地 AI 味启发式扫描。
- Style DNA 表层统计分析。
- 可选模型语义文体分析。
- 多份参考文本按权重融合为综合 Style DNA。
- 参考文本非可逆 18 字符 shingle 哈希签名与输出重合检查。
- 本地项目存储骨架。
- 基础单元测试与 GitHub Actions CI 配置。

### 当前限制

- 人物、事件、伏笔在章节生成后尚未自动回写结构化状态。（2026-09-14 已解决：`novel_ai/memory.py`）
- 长篇 Recall 目前只有近章摘要接口，尚未接入向量 RAG / 知识图谱。
- Style Lab 的多来源权重目前在会话中设置，尚未有完整的 profile 编辑器。
- 没有冻结的真实小说 A/B benchmark，因此不能声称当前生成质量已经达到目标。
- GitHub Actions workflow 已创建，但本轮连接器没有返回 push-triggered run，因此 CI 通过状态仍需后续确认。

### 下一阶段

1. 章节后处理：自动抽取事实、人物状态变化、伏笔、时间线和章节摘要。
2. Context Assembler：Canon + Active + Recall 三层记忆。
3. 固定测试集：至少覆盖都市、玄幻、悬疑等不同题材的章纲扩写。
4. 建立人工评分表：情节、人物、连续性、自然度、AI 味、章末拉力。
5. 根据 A/B 结果决定是否引入向量数据库 / 知识图谱，避免为了架构复杂度而复杂。

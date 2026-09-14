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

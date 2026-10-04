# Novel 最终目标与成果整理索引

> 只读核验快照：2026-10-04 18:29 UTC。仓库 ID：1338612403；实际仓库：Jvust1/Novel；默认分支：main。
> 本文是新增的检索、去重与验收索引，不替换 North Star、现有治理文件、历史证据或作者决定。所有状态绑定下述 SHA；后续提交须重新核验。

## 1. 当前应该从哪里开始

1. 当前正式读取链：[README](https://github.com/Jvust1/Novel/blob/e3e3c9218bd74f3c7b0f90e23106af9f8ced7a96/README.md) → [AGENTS 顶部当前入口](https://github.com/Jvust1/Novel/blob/e3e3c9218bd74f3c7b0f90e23106af9f8ced7a96/AGENTS.md) → [GPT 写作入口](https://github.com/Jvust1/Novel/blob/e3e3c9218bd74f3c7b0f90e23106af9f8ced7a96/docs/GPT_WRITING_ENTRY.md)。
2. 当前工程指针：[current_candidate.json](https://github.com/Jvust1/Novel/blob/e3e3c9218bd74f3c7b0f90e23106af9f8ced7a96/governance/current_candidate.json) → [main_release_candidate.json](https://github.com/Jvust1/Novel/blob/e3e3c9218bd74f3c7b0f90e23106af9f8ced7a96/governance/main_release_candidate.json) → [MAIN_RELEASE](https://github.com/Jvust1/Novel/blob/e3e3c9218bd74f3c7b0f90e23106af9f8ced7a96/docs/MAIN_RELEASE.md)。
3. 长期目标：[PROJECT_NORTH_STAR](https://github.com/Jvust1/Novel/blob/e3e3c9218bd74f3c7b0f90e23106af9f8ced7a96/docs/PROJECT_NORTH_STAR.md)；工程约束：[ARCHITECTURE_INVARIANTS](https://github.com/Jvust1/Novel/blob/e3e3c9218bd74f3c7b0f90e23106af9f8ced7a96/docs/ARCHITECTURE_INVARIANTS.md)。当前 GPT/私有 Drive 写作入口优先于历史本地启动清单。
4. 追溯而非替换当前指针：[CURRENT_STATE](https://github.com/Jvust1/Novel/blob/e3e3c9218bd74f3c7b0f90e23106af9f8ced7a96/docs/CURRENT_STATE.md)、[DECISION_LEDGER](https://github.com/Jvust1/Novel/blob/e3e3c9218bd74f3c7b0f90e23106af9f8ced7a96/docs/DECISION_LEDGER.md)、[EVALUATION_LEDGER](https://github.com/Jvust1/Novel/blob/e3e3c9218bd74f3c7b0f90e23106af9f8ced7a96/docs/EVALUATION_LEDGER.md)、[HANDOFF](https://github.com/Jvust1/Novel/blob/e3e3c9218bd74f3c7b0f90e23106af9f8ced7a96/docs/HANDOFF.md)、[project_state](https://github.com/Jvust1/Novel/blob/e3e3c9218bd74f3c7b0f90e23106af9f8ced7a96/governance/project_state.json)、[artifact_manifest](https://github.com/Jvust1/Novel/blob/e3e3c9218bd74f3c7b0f90e23106af9f8ced7a96/governance/artifact_manifest.json)。

核验过的 main 是 `e3e3c9218bd74f3c7b0f90e23106af9f8ced7a96`。current_candidate 已明确将 project_state/artifact_manifest 标为历史清单。历史 project_state 的 pending_sync=[] 不是当前所有私有产物已同步的证明；本次没有读取或同步私有小说，也没有改写这些记录。

插件/技能/开源前检：本次使用已连接 GitHub 插件读取实际 ref、文件、PR、比较与 CI；已读取工程技能和仓库开源复用/许可策略。本次只新增整理文档，复用既有协议与证据，不新增运行库、模型调用、服务或凭据。

## 2. 最终目标 → 已有路径 → 仍缺的验收

最终目标是中文网络小说共同作者、连续性编辑与文风编辑：多参考材料的高层 Style/Story/Market DNA → 原创长篇 → 作者可控的审校与续写。不能用组件数量代替情节、人物、连续性和自然表达的真实改善。

| 目标 | main 已有权威路径 | 当前证据等级与剩余验收 |
|---|---|---|
| GPT 内可恢复、作者可控的写作 | GPT_WRITING_ENTRY；novel_ai/gpt_story_state.py；gpt_story_journal.py；memory_proposals.py；writing_templates/story_state.template.json | 已有协议与执行代码；真实故事需要作者指定私有来源、版本确认、实际保存读回。源码可读不等于代码执行。 |
| 因果规划与层级大纲 | novel_ai/outline.py；outline_markdown.py；author_workflow.py；engine.py；prompts.py | 工程路径已存在；需要冻结真实章节对照来证明因果、节奏和章末拉力。 |
| 角色知识、长期连续性与安全续写 | novel_ai/context.py；memory.py；accepted_writing.py；history_recall.py；recall_backends.py；docs/ACCEPTED_HISTORY_REBUILD.md | 多层记忆、来源指纹及候选隔离已有工程证据；可选 Recall 的真实运行、误召回/错误记忆与长篇收益须独立验证。 |
| 自然文风与原创性 | novel_ai/style_engine.py；story_dna.py；reference_pack.py；originality.py；dialogue_attribution.py；docs/prompts/natural-fiction/ | 现有派生特征、提示与启发式检查不能证明“去 AI 味”、原创性或商业成功；需要真人盲评和受控 A/B。 |
| 不丢稿、可恢复、接受稿可审阅 | novel_ai/storage.py；storage_guard.py；settings_commit.py；style_commit.py；accepted_export.py；docs/SETTINGS_SAVE_RECOVERY.md | 已有恢复与导出实现；当前 main 的 Windows 并发存储回归失败仍是明确未关闭门禁。 |
| 前三章/前20章市场可读性 | novel_ai/market_eval.py；release_eval.py；release_pack.py；benchmarks/ | 工具/样例与历史运行已存在；作者接受、独立读者评分、平台结果各需要对应证据，不能由 CI 替代。 |

这些路径均在上述 main 树中核实存在；“有文件/适配器”不等于本次已执行或部署。

## 3. 活跃分支和成果边界

| 项目线 | 精确 checkpoint | 可确认事实 |
|---|---|---|
| main | `e3e3c9218bd74f3c7b0f90e23106af9f8ced7a96` | [#76](https://github.com/Jvust1/Novel/pull/76) 已合并；之后增加插件/技能/开源启动前检。最新 push CI 仍有 Windows 失败，见下一节。 |
| occurrence-aware voice review [#78](https://github.com/Jvust1/Novel/pull/78) | fix/voice-occurrences-20261004 @ `63080d8c94f55f95c820e10ee8cd31509afee27a` | 独立 draft；GPT 提示/声线证据修复；未合并。本整理不恢复该线开发。 |
| 开源发现 [#79](https://github.com/Jvust1/Novel/pull/79) | research/oss-discovery-20261004 @ `43a3f78aac60f995c2f1a729ecf766145f7918b5` | 发现候选文档，不是运行时集成。 |
| 开源融合 [#80](https://github.com/Jvust1/Novel/pull/80) | feat/oss-code-fusion-20261004 @ `c75e5074b2196bd7ddcae80590289a812778d4d3` | draft；14 个来源移植/算法适配与6个可选适配器的记录；当前 exact-head CI 成功。并不代表20个完整上游运行时已安装、部署或有文学收益。 |
| 新20项目录 | feat/oss-20-catalog-20261004 @ `ebb9a29a33907892fa61929c9cdc61b0f18b4514` | 该 head 比 #80 多2个提交、仅3个新增文件：docs/OSS_20_VALIDATED_20261004.md、novel_ai/oss_batch_20261004.py、tests/test_oss_batch_20261004.py。新增层是目录/筛选及两项测试；继承 #80 代码不能重复计为20个新增实际集成。 |
| 长篇样例归档 [#77](https://github.com/Jvust1/Novel/pull/77) | chore/sync-longform-sample-20261002-v1 @ `627133b0516697773403bcf85fe2e57bc87f91c0` | 独立元数据归档 PR；其正文说明样例仍是候选，未获得作者接受、真人盲评或平台批准。本次未验证其私有原件。 |

新目录分支与本整理文档分支并行；本整理不修改任何 feat/oss-* 分支或运行文件。目录分支的后续推进以新 SHA 为准。

## 4. 开源数量与许可：统一计数口径

- main [open_source_registry.json](https://github.com/Jvust1/Novel/blob/e3e3c9218bd74f3c7b0f90e23106af9f8ced7a96/governance/open_source_registry.json) 实际有61条、61个不同 repo 标识；这是混合采用方式的注册条目数量。
- main [OPEN_SOURCE_INTEGRATION.md](https://github.com/Jvust1/Novel/blob/e3e3c9218bd74f3c7b0f90e23106af9f8ced7a96/docs/OPEN_SOURCE_INTEGRATION.md) 的旧标题仍写47 projects，部分历史状态写38。它们属于不同历史快照，不应累加或解释为61项全部执行完毕。
- 新目录的 PROJECTS=20、safe_only=20，仅表明快照元数据满足它自己的字符串过滤。find_spec 只能表明模块可发现，不能证明调用成功、调用来自真实主路径或许可证义务已履行。
- #80 的14+6与新目录的20并非同一集合；应按规范化上游 repo＋采用能力去重，分别列明已有/新增、来源移植/可选适配/外部运行时/研究候选。
- 沿用现有许可策略：保留精确上游提交、适用许可证/NOTICE、移植范围与调用点。无许可证只作参考；AGPL默认外部/参考。星标是采样时数值，不能代替许可证审查、测试、质量或安全证明。
- 每个待验收条目最低证据：上游 pin → 许可/NOTICE → Novel 真实调用点 → 真实依赖或替身说明 → focused test → 最终 head CI → 作者/真人质量结果（若声称质量提升）。缺哪一级就写哪一级未验证。

## 5. PR 去重与依赖关系

本快照从 pulls?state=open 实读51个开放 PR；计数不包含本整理 PR。开放状态与实现是否已经进入 main 是两个不同问题。

### 已进入 main 的历史主线

历史接受/续写/导出/来源/恢复主线为：

`#50 → #51 → #52 → #53 → #54 → #56 → #61 → #62 → #63 → #64 → #65 → #66 → #67 → #68 → #69 → #70 → #72 → #73 → #74 → #75 → #76(main release)`

[#73](https://github.com/Jvust1/Novel/pull/73) 还明确整合了 [#71](https://github.com/Jvust1/Novel/pull/71) 的 Unicode CLI 修复，同时保留原分支历史。API ancestry 比较确认：#51 head 是 main 祖先（main ahead23/behind0）；#75 head 也是 main 祖先（ahead3/behind0）。因此这些开放历史 PR 不能全部再作为“尚未交付的独立功能”排期；也不能因原 PR 仍 open 就否认 #76 的真实集成回执。这里不关闭、合并或重命名任何历史 PR。

### 另一基线的重复候选

- [#55](https://github.com/Jvust1/Novel/pull/55) 与 #51 都从 #50 延伸接受历史修复，但不是同一个提交链。main 相对 #55 为 diverged（ahead25/behind1）。
- [#57](https://github.com/Jvust1/Novel/pull/57) 与 [#58](https://github.com/Jvust1/Novel/pull/58) 同名预算修复，都基于 #55；main 相对两者均 diverged（ahead25/behind2）。#58 的累计输入语义更完整是其 PR 描述，并不自动证明可整体替代 main。
- `#55 → #58 → #59 → #60` 是另一条候选链。[#62](https://github.com/Jvust1/Novel/pull/62) 只移入 #60 的质量门禁方案，明确未整体纳入上述功能链。后续只评审 main 尚缺的具体差异，禁止整链回灌覆盖新代码。
- #71/#72 是平行切片，由 #73 明确整合；不要重复应用两个来源及其整合补丁。
- #78 与 #80 在本快照的 changed-file 集合没有直接重叠；这不证明语义兼容。若未来整合，仍需最终组合 head 的回归与当前入口检查。

更早候选 #1–#3、#13–#26、#33 留作来源/历史；需先按现有 Decision Ledger 的 additive-port 记录和 main 实际差异判断是否仍有独立缺口，不因标题重复就删 PR。

## 6. 真实 CI 与验收缺口

| 精确 head | 当前读取结果 | 结论范围 |
|---|---|---|
| main `e3e3c921` | [push run 37135661966](https://github.com/Jvust1/Novel/actions/runs/37135661966)：Ubuntu3.11/3.12 成功；Windows3.11/3.12 失败 | 两个失败日志都是 tests/test_storage_integrity.py::test_cooperating_processes_do_not_lose_summaries，ValueError: 项目目录越界；各1 failed /2239 passed /17 skipped。不能用旧 #76 绿色覆盖。 |
| #78 `63080d8c` | [run37196661853](https://github.com/Jvust1/Novel/actions/runs/37196661853)：3个job成功，Windows3.11失败 | 同一个并发存储用例；1 failed /2281 passed /17 skipped。只记录，不重试或继续修复该暂停工作。 |
| #80 `c75e5074` | [run37220643014](https://github.com/Jvust1/Novel/actions/runs/37220643014)：completed/success | 仅覆盖该提交的工程 workflow；不能外推为新目录 head、真实可选SDK全部安装或文学验收。 |

EVALUATION_LEDGER 区分了历史真实运行和合成/替身工程测试。E-001 是 RUN_EXECUTED_AWAITING_HUMAN_SCORE；E-002 是 SPEC_DEFINED_NOT_YET_RUN；E-003 是 IMPLEMENTED_AWAITING_FROZEN_EVAL。没有本次新增真人评分，因此不能宣称最终目标已完成或开源数量提升了小说质量。

## 7. 下一步顺序与完成条件

1. **锁定唯一实施基线。** 当前正式入口仍读 main；新开源工作分别标注 base/head、保留已有作者确认与安全恢复。文档修改不移动 current_candidate 指针。
2. **先核对现有 Windows 并发存储失败。** 保存当前失败日志，建立可重现原因与修复验证；只有明确授权的后续工程任务可修改代码。本整理不擅自重试、改测试或恢复暂停 PR。
3. **把新20项目录补成逐项验收表。** 每项关联最终目标、已有/新增、真实调用点、许可pin、离线/真实SDK测试及失败回退；没有接线的项目保持 catalog-only。优先复用当前可用插件/技能与既有实现。
4. **收敛 PR 差异。** 以 main 已集成主线为基线；单独评审 #55/#57/#58/#59 尚存差异及 #78/#80 的组合兼容性。保留历史、不自动整链合并。
5. **冻结最小真实质量闭环。** 沿用现有都市/玄幻/悬疑样例及12维评分，明确单变量，先取得受控模型运行与真人评分，再决定启用哪些可选 Recall/结构化后端。需要新费用、凭据、私有材料或第三方传输时另行取得具体授权。
6. **闭合长篇和审阅交付。** 从作者明确接受的版本导出3/20章审阅包，验证来源、顺序、读回与恢复；把工程通过、作者接受、独立盲评、平台表现分别记录。#77 的候选样例不自动升级为接受证据。

本文件的完成条件是：来源、分支、重复链、证据等级和下一步可被核对。它不宣称已运行测试、修复代码、部署、同步私有产物或完成小说质量验收。

# 已接受历史重建与下一章预检

本候选层解决“只使用作者认可的历史版本”这一连续创作缺口。它叠在 `fix/final-output-gates-20261001` 上，不改写旧接受记录，不把当前候选稿、未来章节或其他故事的数据自动当成历史事实。

## 1. 目标

下一章开始前，执行器需要从**实际读回**的故事档案重新建立连续性资料，而不是相信上一会话留下的缓存：

1. 只读取 `accepted_chapters` 中已经完成计划确认、正文确认、记忆确认并应用的章节；
2. 使用接受记录绑定的精确计划/正文来源重新计算可派生资料；
3. 当前未接受计划/正文仍可作为“本章 Active 候选”存在，但绝不能被当作历史来源；
4. 换故事、故事版本/Canon/Active/Recall/文风发生实质变化、已接受来源变化或调用方持有旧历史指纹时明确拒绝；
5. 下一章上下文预算不足时阻塞，而不是为了塞入预算悄悄截断必要连续性资料。

该能力是工程来源门禁，不证明文学质量，也不认证真人身份。作者接受仍由 GPT 写作协议中的明确确认记录提供。

## 2. 新接口

### `rebuild_accepted_history(...)`

输入已经通过 `load_state(...)` 实际读回的 `StoryState`，重建：

- `history_chapter_ids`：严格来自接受历史的章节 ID；
- 每章计划/正文的 `source_fingerprint` 与版本绑定；
- 从**已接受正文**重新计算的角色 Voice DNA 与聚合基线；
- 从能解析为 `ChapterPlan` 的**已接受计划**重新计算 Story DNA 结构；不能解析时保留 `unparsed`，精确计划原件仍可作为来源使用；
- 接受后 Active 连续性字段：当前时间、地点、近章摘要、开放伏笔、禁揭信息；
- `accepted_history_sha256`：绑定故事 ID、故事 revision、当前 Canon/Active/Recall/文风摘要及全部已接受计划/正文来源指纹。

`accepted_history_sha256` **不绑定当前 JSON 文件整体 SHA**。原因是保存新章的未接受计划/草稿会改变文件字节，但不会改变已接受历史；这种候选级变化应允许复用同一历史指纹。实际文件 SHA 仍单独保留为 `readback_file_sha256`，证明本次确实读了哪个文件。

故事已有接受历史时，如果没有 `load_state(...)` 产生的当前 `verified` 读回，重建会拒绝。`expected_story_id` 和可选 `expected_history_sha256` 用于拦截换书缓存与过期历史快照。

### `preflight_next_chapter_context(...)`

在已有 `preflight_context(...)` 上增加下一章连续性入口：

- 当前章节必须已 `start_chapter`，且尚未应用本章记忆；
- 先重建已接受历史；
- 最近若干章的已接受计划和正文按**完整 artifact**加入可选历史来源，预算允许才整体加入，不截断；
- 另外加入紧凑的 `ACCEPTED HISTORY ONLY` 派生区，包含历史指纹、接受章节列表、Active 连续性、Voice 基线和最近计划结构；
- 当前本章计划/正文只按现有 Active 规则进入，不会混入历史列表；
- `history_bytes` 单独计入预算；调用者的 `reserve_bytes` 保留原语义。

## 3. 修复：改计划后旧候选不再泄漏进提示

原状态机有意保留旧正文，便于审计和在新计划确认后由作者显式重新绑定。但旧 `preflight_context(...)` 只判断 `progress.draft` 是否存在，会在计划已经换版、`draft_plan_revision` 仍指向旧计划时把这份旧正文继续塞进提示。

现在只有 `draft_plan_revision == plan_revision` 时，当前 draft 才进入必要上下文。旧候选仍保留在状态档案中，但不会作为当前提示内容，直到调用者明确 `set_draft` 把正文绑定到新计划版本。

## 4. CLI

现有 `scripts/story_state.py` 新增 `accepted-history` 与 `next-preflight`。两条命令都会先真实读取目标 JSON 并建立读回证据。`next-preflight` 不替作者执行 `start_chapter`、确认计划或接受正文；这些仍通过既有显式 command 流程完成。

## 5. 反例与恢复边界

新增检查覆盖：

- 计划换版后旧 draft 仍留档，但不再进入 prompt；
- 已应用但尚未保存/读回的章节不能充当可信历史；
- 只从已接受计划/正文重建结构与角色口吻；
- `expected_story_id` 阻止其他书缓存；
- 旧 `accepted_history_sha256` 阻止接受历史/上下文来源变化后继续使用旧快照；
- 保存当前未接受候选导致整个文件 SHA 改变时，只要接受历史及基础连续性未变，历史指纹保持稳定；
- 重新启动、重新 `load_state` 后可得到相同的历史指纹；
- 历史连续性块本身塞不进预算时明确 `blocked=true`；
- CLI 的 accepted-history / next-preflight 走真实文件读回，而不是仅校验内存对象。

本地当前环境的专项验证：`tests/test_gpt_story_state.py` 与 `tests/test_gpt_candidate_review.py` 合计 **77 passed**。当前容器缺少 Streamlit，不能在本地声明仓库全量通过；完整 Python 3.11/3.12 矩阵由 GitHub Actions 对候选 PR 精确 head 验证。

## 6. 尚未解决

- 输入 token 的精确 tokenizer 计量与多次模型调用累计预算仍是下一优先级；本轮仍使用确定性的 UTF-8 字节预算；
- 只重建已有 `accepted_chapters` 能证明的历史；缺失原始接受档案时不会根据聊天摘要补造；
- Story DNA 来自已接受的结构化计划，不等于从最终正文重新抽取完整事件；
- Voice DNA 是确定性对白归属统计，不替代真人对人物口吻的文学判断；
- 本轮不自动应用新的记忆候选，不改变“模型提取 → 作者确认 → 才可正式写入”的边界；
- 不实现 Drive 多文件事务、多设备锁、历史正文自动重写或真人作者身份认证。

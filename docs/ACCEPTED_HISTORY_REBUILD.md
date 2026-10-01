# 已接受历史重建与下一章恢复候选

本候选接在 fix/final-output-gates-20261001 / Draft PR #50 之上。目标不是改写已有小说，而是让 GPT 对话写作在换会话、重新加载、重做计划后，只从作者已经接受并保存的版本恢复下一章所需历史，避免旧候选重新混入提示。

当前候选分支：fix/accepted-history-rebuild-20261002。未合入 main，不自动部署，不公开私人正文，也不产生付费模型调用。

## 1. 解决的具体风险

此前 set_plan 会保留旧正文作为可复核候选，这是为了不丢稿；但 preflight_context() 会无条件把 progress.draft 放进提示。作者换了计划后，旧正文虽然失去接受资格，仍可能重新进入下一次模型上下文。

本候选把“保留候选”和“允许进入提示”分开：

- 旧正文仍保留在私有状态中，便于作者比较或重新绑定；
- 只有已经绑定当前已接受计划的正文才可进入当前提示；
- 改计划后，旧正文即使仍在 JSON 中，也不会进入 context_text；
- 重新接受新计划后，仍须显式 set_draft 重新绑定正文，新计划不会自动继承旧稿。

## 2. 已接受历史快照

新增 accepted_history_snapshot(state, include_text=True) 和 accepted_history_fingerprint(state)。

快照只从 accepted_chapters 重建。现有校验器逐章核对故事 ID、基础/结果故事版本、chapter_id、计划/正文版本、实际来源、三个作者确认记录和已应用的 memory_update_id。因此快照不会读取当前未接受计划或正文、已失效记忆候选、未来章节、另一本书状态，或没有被接受记录绑定的外部缓存文本。

include_text=False 只隐藏计划/正文文本用于紧凑清单；历史 SHA-256 仍按完整已接受记录计算，所以清单视图和全文视图共享同一个 accepted_history_sha256。

历史指纹同时绑定 accepted_context_sha256，也就是当前经验证的 Canon、Style、Active、Recall。新增未接受计划或草稿不会改变它；真正接受并应用的新章节或明确接受的上下文变更会改变它。

## 3. 下一章上下文

preflight_context() 始终加入紧凑 accepted_history 清单，记录本书已接受章节的来源和历史指纹，但不默认把整本小说全文塞进上下文。

如果下一章确实需要某些历史正文原件，调用 accepted_history_chapter_ids 显式点名，例如 chapter-017、chapter-021。点名章节会以 ACCEPTED HISTORY ONLY 段进入上下文，计划和正文都直接来自对应接受记录。

如果章节 ID 不属于本书已接受历史，直接拒绝，不去其他缓存、未来章节或同名文件猜测。被点名历史属于必需上下文；预算不足时返回 blocked=true，保留完整文本并报告不足，不为了过预算静默截断或删除。

普通 Recall 仍可按原有规则筛选。Canon、人物知识、禁揭信息、当前计划、当前有效正文、明确必需来源和明确点名的已接受历史继续作为不能静默裁剪的内容。

## 4. CLI 恢复入口

读取实际保存文件并重建已接受历史：

    python scripts/story_state.py accepted-history /private/story.json --story-id stable-book-id --revision 12 --sha256 ACTUAL_SHA256

只看来源清单：

    python scripts/story_state.py accepted-history /private/story.json --story-id stable-book-id --manifest-only

下一章预检点名历史原件：

    python scripts/story_state.py preflight /private/story.json --sources /private/read-sources.json --budget-bytes 60000 --reserve-bytes 10000 --accepted-chapter chapter-017 --accepted-chapter chapter-021

accepted-history 内部先走 load_state()。故事 ID、期望 revision 或实际文件 SHA 不一致时拒绝。对已经成功写入的状态，load_state() 产生本次真实读回凭据；旧聊天里记住一个 JSON 片段不等于重新读回。

真正进入下一章仍使用现有 start_chapter 操作：上一章处于 ready_next 且本次加载产生 verified readback 后才能启动。本候选没有新增绕过作者确认的自动续写动作。

## 5. 反例与验证

新增专项覆盖：

1. 改计划后，保留的旧正文仍在状态中，但不再进入预检提示。
2. 保存、重新加载、新开章节、新计划和未接受正文后，历史快照仍只含上一章已接受版本。
3. 未接受候选不会改变 accepted_history_fingerprint。
4. 显式点名已接受章节时，完整计划和正文进入上下文；预算少 1 字节即阻塞，不截断。
5. 请求不存在、未来或其他书的章节 ID 时直接拒绝。
6. CLI 从实际保存文件读回后可重建 manifest/full snapshot。

本地 Python 3.13.5：
- test_gpt_story_state.py + test_gpt_candidate_review.py：77 passed。
- 五组 GPT 状态、日志、入口测试分别 54 + 23 + 20 + 11 + 18 = 126 passed。
- py_compile 对 novel_ai/gpt_story_state.py 与 scripts/story_state.py 通过。
- 完整 pytest 收集阶段只因当前容器缺少 Streamlit，被 tests/test_app.py 和 tests/test_author_ui.py 的两个 ImportError 阻塞；这不是断言失败。

完整 Linux Python 3.11 / 3.12 仍以 GitHub Actions 为最终工程回归证据。

## 6. 仍未解决

- 不证明数十万字小说的文学质量或人物声音长期稳定。
- 不自动决定哪些历史章与下一章最相关；可使用现有 accepted-summary Recall / semantic Recall 做候选筛选，但最终需要的原件仍须显式绑定。
- 不把模型提取的 Voice DNA、Story DNA 或记忆候选自动升级为正式事实；作者接受边界不变。
- 不提供 Drive 跨文件事务或多设备锁；私有 Drive 的实际保存/读回仍须当前工具真实完成。
- 不改写历史正文，不自动重算已接受历史记忆；作者设定/文风变更继续走 GPT_AUTHOR_AMENDMENTS.md 的复审流程。
- 输入 token 精确计量和多次模型调用累计预算属于后续任务；本候选继续使用确定性 UTF-8 字节门。

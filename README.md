# Novel：在 GPT 中写长篇小说

通过 GPT 的 GitHub 插件读取本项目，在对话里完成规划、起草、审校与局部修订。作品的正文、人物、设定和进度保存在作者指定的**私有 Drive**。这条入口不要求用户本地安装程序、配置 API Key 或运行 Python。

作者改设定或文风后的安全续写：[变更提案 → 影响复审 → 保存读回](docs/GPT_AUTHOR_AMENDMENTS.md)，保留旧稿和确认记录。

执行器存稿与评测证据：[路径约束、原子写入、摘要中断恢复和评分保护](docs/STORAGE_INTEGRITY.md)。

明确选择的本地语义召回现可进入实际写作上下文：[来源验证与失败状态保护](docs/RECALL_INTEGRITY.md)。

换稿后报告与正文一致：[共享审校、版本证据和模型输出边界](docs/FINAL_OUTPUT_GATES.md)。

换会话/重做计划后的历史恢复：[只从作者已接受版本重建下一章上下文](docs/ACCEPTED_HISTORY_REBUILD.md)。

模型调用不再只有单次输出上限：[完整输入计量与 retry/fallback 累计预算](docs/MODEL_CALL_BUDGETS.md)。

记忆抽取与正式故事事实分离：[候选 → 作者确认 → 幂等回写](docs/MEMORY_ACCEPTANCE_GATES.md)。

工程回归与审计边界：[依赖一致性、致命 Ruff 硬门与默认 Ruff 维护性基线](docs/QUALITY_GATES_AUDIT.md)。

## 从这里开始

1. 读取 [AGENTS.md](AGENTS.md) 和 [GPT 写作入口](docs/GPT_WRITING_ENTRY.md)，核对实际读取的分支或提交
2. 读取当前作品的私有故事档案；新书从 [空白故事状态模板](writing_templates/story_state.template.json) 开始，未确定的资料留空
3. 按本书类型选择 [文风卡](docs/prompts/natural-fiction/GENRE_PROFILES.md)，依次使用 [写前](docs/prompts/natural-fiction/01-writing-before.md)、[审校](docs/prompts/natural-fiction/02-editorial-review.md)、[局部修订](docs/prompts/natural-fiction/03-local-repair.md) 提示
4. 作者确认具体版本后，更新私有故事档案并读回核对，供下次对话继续

可直接告诉 GPT：

> 通过 GitHub 插件读取 Jvust1/Novel 的 chore/quality-gates-audit-20261002 分支，先读 README.md、AGENTS.md 和 docs/GPT_WRITING_ENTRY.md，再读取我指定的私有 Drive 故事档案。已有作品恢复到当前阶段；新书先确定类型、主角与核心冲突。先给场景计划，等我确认后写正文；未接受的候选不进入正式记忆。

如果插件没有读到该分支或 Drive 文件，GPT 应说明缺少哪个来源，请作者提供可访问的位置；不能假装已加载。上述分支入口尚未合入 `main`，默认分支内容未必相同。

## 文件与能力边界

- GitHub：写作规则、空白模板、来源许可和明确授权公开的原创演示；不默认公开真实作品或个人创作进度
- 私有 Drive：真实作品正文、人物卡、参考资料、候选稿、已接受版本与恢复状态；读写能力以当前会话实际工具为准
- [文风提示包](docs/prompts/natural-fiction/README.md)：都市/日常、言情、悬疑、玄幻/仙侠、奇幻、科幻、历史、武侠、恐怖九类候选配置，每本书选自己的声音
- [读者信息揭示账本](docs/READER_REVEAL_LEDGER.md)：术语首次出现、读者已知与完整真相分开，已确认章计划决定本章允许揭示的范围
- [可选状态检查](docs/GPT_STATE_CHECKS.md)：有实际执行器时核对版本、确认、保存恢复与上下文预算；不会替用户自动接受内容
- [原创插件演示](writing_demos/plugin-first-chapter-20261001/README.md)：仅为公开测试作品，不是用户真实小说，也不是已被作者接受的稿件
- [本地作者工作台](docs/AUTHOR_WORKFLOW.md)：保留现有 Streamlit、provider 和工程能力，供确实需要运行程序的人使用；它不是 GPT 写作的前置条件

GitHub 文件可读不等于代码已经执行。没有执行器时，只能按文本协议写作与审读，不能声称跑过 Python、算出文件哈希或通过程序测试。AI 审读不等于独立真人盲评，也不承诺检测器通过率、签约或爆款。

[Project North Star](docs/PROJECT_NORTH_STAR.md) 的原创、连续性和自然表达目标保持不变。[交接状态](docs/HANDOFF.md) 说明工程分支与历史记录；先按本入口恢复当前写作任务。

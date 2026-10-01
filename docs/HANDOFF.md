# 当前交接 — 2026-10-01

当前工程候选：`fix/accepted-history-rebuild-20261001`，直接叠在 Draft PR #50 的 head `35208537aa1fb830a2325ec1dd8870bdf0564190` 上。新增范围只处理[已接受历史重建与下一章预检](ACCEPTED_HISTORY_REBUILD.md)；#50 的最终稿审校、输出额度与严格 JSON 保持为冻结基线。执行代码提交 `7f2b93367661b0038bab2885851fed607f047882` 的 CI run 36856263295 已验证 Python 3.11/3.12 均为 1206 passed / 1 skipped；以下旧候选记录继续保留。

当前用户使用路径：GPT 通过 GitHub 插件读规则 → 读取可访问的私有 Drive 故事状态 → 按作品类型规划、起草、审校和局部修订 → 作者按版本接受 → 私有保存并读回 → 下次对话恢复。先读 [GPT_WRITING_ENTRY.md](GPT_WRITING_ENTRY.md) 和 `AGENTS.md` 顶部；不要求本地安装。North Star 与既有代码保留。

- 当前本地 Recall 完整性候选入口为 `fix/recall-integrity-20261001`，叠在已验证 [Draft PR #48](https://github.com/Jvust1/Novel/pull/48) 上；#48 head `78cb607a8b4ae9cade68a62b7065a8f08e85ace0` 保留不动，精确提交双版本 CI 成功且各 632 passed / 1 skipped。各候选均未合入 `main`。
- [本地语义 Recall 完整性](RECALL_INTEGRITY.md) 修复失败更新的文本/向量错配，并作为显式本地选项接入实际写作上下文；默认召回保持不变；显式历史范围会省略尚未绑定目标章节/状态版本的旧长篇告警，并记录原因。未指定范围的旧调用不构成旧章改写安全入口，真实模型/加速器质量未验证。
- [存稿与评测证据保护](STORAGE_INTEGRITY.md) 接入实际 ProjectStore 和 benchmark：保留旧文件、固定两文件恢复意图、合作进程锁、独占评测目录及人工评分不覆盖。
- 新增 [作者设定/文风变更日志](GPT_AUTHOR_AMENDMENTS.md)：保留旧稿与接受历史，明确确认、影响复审、保存读回后继续；历史正文替换与记忆重算仍未实现。
- 现有本地作者工作流已发布为 [Draft PR #45](https://github.com/Jvust1/Novel/pull/45)，head `d14ccae8faa90fb4e293ff7f448c8d6ee03f4d90`。[该提交 CI](https://github.com/Jvust1/Novel/actions/runs/36826620415) 成功，413 passed / 1 skipped；未合并。用法见 [AUTHOR_WORKFLOW.md](AUTHOR_WORKFLOW.md)。
- [原创插件演示](../writing_demos/plugin-first-chapter-20261001/README.md) 已在提交 `badcfab4d925a1fbe464b4a314cf9abf004a675b` 发布并通过插件读回；它仍是待作者审阅的公开测试候选，不代表真实用户作品可公开或已被接受。
- 文件读取不代表 Python 执行；GPT 入口是对话与归档协议，不是自动运行的新后端。真实故事质量、独立真人评测和平台结果仍需各自的证据。
- CURRENT_STATE / EVALUATION_LEDGER 中此前的 local-only、未推送描述是对应阶段的历史快照，不能覆盖以上已发布状态。旧 PR #33 不是本轮的接受记录。

本地作者候选的历史起点保留为连续性快照 tree `2c910626a27a3cc14393af91e6dd6aae6ee3a2b9`，源于当时 main `bf37f1906636791f03c6a6ce1eecd3cc81a6a803` 加先前本地成果；它不是当前分支 head。

以下旧交接与恢复清单保留供追溯；其中全项目启动、本地 CI 优先级等不再作为当前 GPT 写作的默认要求。

# Handoff

## Novel v0.1-dev

### 先做什么

1. 读取 Drive 根目录 `00_全项目总入口_新AI先读此文件` 及所有 `全项目_` 文件。
2. 读取 `AGENTS.md` 和 `governance/project_state.json`。
3. 读取 North Star / Architecture Invariants / Current State / Ledgers。
4. 不要假设本聊天记录是最新项目状态。

### 当前已经存在的可运行内核

- `app.py`：Streamlit 本地写作工作台。
- `novel_ai/provider.py`：OpenAI-compatible provider。
- `novel_ai/models.py`：人物、Story Bible、场景计划、Style DNA、审校数据结构。
- `novel_ai/prompts.py`：章纲规划、正文、审校、修订、语义风格分析协议。
- `novel_ai/style_engine.py`：统计风格、加权融合、参考哈希、AI 味启发式扫描。
- `novel_ai/storage.py`：本地项目/章节/记忆存储。
- `novel_ai/engine.py`：Plan → Draft → Review → Repair 主流程。

### 当前最重要的缺口

**不要先美化 UI。** 2026-09-14 起，前三项已完成：

1. ~~章节生成后自动抽取并回写：人物状态、人物知识、事件、时间线、伏笔、摘要。~~ → `novel_ai/memory.py` + `engine.extract_memory` + app.py"抽取本章记忆并回写"。
2. ~~Context Assembler：Canon / Active / Recall 三层记忆。~~ → `novel_ai/context.py`，带字符预算。
3. ~~固定小说章纲 A/B benchmark。~~ → 已冻结 `benchmarks/`（novel-ab-v1，哈希锁定）+ `novel_ai/eval.py` 运行器 + 评分表工具（E-001 PENDING_RUN）。
4. **当前第一优先：①把本地 CI 修复（`pyproject.toml`）提交推送，让 main 的 ci 变绿；②真实跑一轮 A/B（`scripts/run_benchmark.py`，需要模型端点），人工评分后用 `scripts/aggregate_scores.py` 聚合并回填 EVALUATION_LEDGER。**
5. 根据评测决定是否引入 RAG / 知识图谱。
6. 可选：DOCX/PDF 参考导入、完整 Style profile 编辑器、伏笔面板。

### 设计警告

- 不要把全文长上下文当作记忆系统。
- 不要把“多 Agent”本身当作质量提升。
- 不要把某作者名直接当作 Style DNA。
- 不要用绝对禁词表粗暴洗稿。
- 不要在未评测前宣称“AI 味已解决”。

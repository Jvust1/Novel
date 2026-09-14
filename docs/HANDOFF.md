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

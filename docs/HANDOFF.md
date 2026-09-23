# Handoff

## Novel v0.1-dev

### 接手顺序

1. 读取 Drive 根目录 `00_全项目总入口_新AI先读此文件` / `全项目` 及动态发现的全部 `全项目_` 基线。
2. 读取 `AGENTS.md`、`SECURITY_POLICY.md` 和 `governance/project_state.json`。
3. 读取 North Star / Architecture Invariants / Current State / Decision & Evaluation Ledgers / artifact manifest / Pre-flight。
4. 不要把聊天记录当作当前项目状态权威。

### 当前可运行内核

- Streamlit 本地写作工作台；OpenAI-compatible provider。
- Context → Scene Plan → Draft → Review → Repair → Re-review → Memory Update。
- Canon / Active / Recall 三层记忆和人物知识边界。
- Style DNA、参考签名与 AI 味启发式检查。
- frozen `novel-ab-v1`：都市 / 玄幻 / 悬疑三用例，首次真实 run 已执行。

### 当前第一优先：关闭 G1 人工质量门

首次真实运行 `run-20260914-153013` 已存在，**不要重跑后冒充 first-real**。当前尚无人工质量结论。

本轮新增 A/B 盲化评分工具（PR #15 / `feat/blind-scoring-workflow-20260923`）：

1. 在持有原始 run 的环境执行 `python scripts/render_blind_scoring_pack.py runs/run-20260914-153013`。
2. 给评分者的只有 `blind_scoring_pack.md` 与 `blind_scoring_sheet.csv`；不要提供或提前查看 `blind_map.json`。
3. 完成 3 用例 × 2 样本 × 12 维 = **72/72** 分值，并为每项保留简短理由。
4. 锁分后执行 `python scripts/aggregate_blind_scores.py runs/run-20260914-153013 --write`，再把聚合结果与限制回填 `EVALUATION_LEDGER`。
5. 只有获得评分证据后，才决定长期记忆层保留/修改、下一个模型档位，以及是否值得引入 vector RAG / knowledge graph。

### 重要边界

- 不要先美化 UI；当前最高风险仍是写作质量证据不足。
- 不修改 frozen benchmark / first-real 历史结果；看过结果的 case 不再称 unseen。
- 不把原稿、参考小说、API 密钥或完整 run 正文提交 GitHub；长期证据按 artifact policy 归档 Drive。
- 模型只负责抽取候选，确定性代码负责幂等、锁定和状态一致性。
- 最多一轮自动 repair + re-review；仍不通过交作者决定。
- 不在 E-001 人工评分前宣称记忆层有效，也不提前引入 RAG / 知识图谱。

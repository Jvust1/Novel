# Novel A/B Benchmark（冻结基准）

本目录是评测的冻结输入：三题材章节扩写用例 + 原始前情。所有文件为项目原创内容，可提交 GitHub。

## 冻结纪律

1. `benchmark_manifest.json` 记录每个用例的 SHA-256；`novel_ai.eval.load_benchmark` 与 `tests/test_eval.py` 会强制校验，改一个字都跑不过。
2. 需要新用例时：新增 `cases/*.json`，重新计算哈希并升级 manifest `version`。不得覆盖旧用例（E-000：看过结果的 case 不再 unseen）。
3. 每个用例自带 `pre_history`（近章摘要、已确立事实、时间线、伏笔、未回收线索），运行时被物化进临时 ProjectStore，供 B 变体的 ContextAssembler 消费。

## 变体（每次只改一个变量）

- `A_baseline`：Bible + 人物卡 + 章纲 + 近章摘要（v0.1 行为）。
- `B_memory`：A 之上注入 Canon/Active/Recall 长期记忆（v0.2 行为）。

## 运行

见 `scripts/run_benchmark.py` 模块注释。密钥只从环境变量读取，不落盘。

## 评分

- 运行结束生成 `runs/<run_id>/scoring_sheet.csv`，人工按 E-000 的 12 维度填 1–5 分。
- 填完后用 `novel_ai.eval.load_scores` + `aggregate_scores` 聚合，结果记入 `docs/EVALUATION_LEDGER.md`。
- `runs/` 在 `.gitignore` 中；正式结果只以聚合数字和结论进入 ledger，章节正文归档 Drive。

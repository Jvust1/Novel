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

### 推荐：盲化人工评分

对已经完成的 run，先生成独立盲化包：

```bash
python scripts/render_blind_scoring_pack.py runs/<run_id>
```

会生成：

- `blind_scoring_pack.md`：只显示匿名样本标签，不显示 A/B 变体、provider 标识或长期记忆注入量；交给评分者。
- `blind_scoring_sheet.csv`：12 维 × 1–5 分，并单独保留 `rationale` 理由列。
- `blind_map.json`：匿名样本到真实 variant 的映射；**评分锁定前不要给评分者查看**。

完成全部评分后：

```bash
python scripts/aggregate_blind_scores.py runs/<run_id> --write
```

聚合器会先要求评分网格完整，再解盲并复用 canonical `aggregate_scores` 计算 A/B 结果，写入 `blind_scores_summary.json`。缺分、未知样本、run/case 不匹配或非法分值都会 fail closed。

### 兼容旧流程

- 运行结束仍生成 `runs/<run_id>/scoring_sheet.csv`，供既有流程使用。
- `novel_ai.eval.load_scores` + `aggregate_scores` 仍保持兼容。
- `runs/` 在 `.gitignore` 中；正文与盲化评分工作文件默认不入 GitHub。正式聚合数字、方法和结论进入 `docs/EVALUATION_LEDGER.md`；需要长期保存的正文/评分证据按 artifact policy 归档 Drive。

# 离线市场可读性评分

`novel_ai.market_eval` 提供绑定语料指纹的人工评分表。它只校验和汇总人工填写的分数，不调用模型，也不生成平台推荐、签约或发布保证。

## 使用流程

先准备自有或已获授权的章节 JSON。`opening_3` 必须包含连续的前 3 章，`retention_20` 必须包含连续的前 20 章。正文不会写入评分表，评分表只保存语料指纹。

```bash
python scripts/market_review.py corpus.json --sheet review.csv
```

人工在 `review.csv` 中为同一位 `reviewer_id` 填写 10 个维度的整数分数（1 到 5），并可补充 `note`。完成后写出汇总：

```bash
python scripts/market_review.py corpus.json \
  --sheet review.csv --aggregate --out review-summary.json
```

创建评分表和写出汇总都使用“只新建”模式：目标文件已存在时命令会报错并保留原文件。请更换输出路径，不要依靠覆盖来重置评分。

## 校验规则

- CSV 表头必须存在且不能有空列名或重复列名；至少包含 `project`、`stage`、`corpus_sha256`、`reviewer_id`、`dimension`、`score`。
- 每行列数必须与表头一致，`score` 必须是 1 到 5 的整数，不能留空。
- 评分必须覆盖 10 个维度各一次，并且项目、阶段、语料指纹和评审者一致。
- 语料正文发生变化后，原评分表会因指纹不匹配而拒绝汇总。

命令行错误会以简短的中文提示返回，不会写出汇总文件。评分结果仍需由人结合正文和编辑目标判断，不能把 `mean_score` 当作商业结果承诺。

# 人物声线统计 v3

本轮针对人物口吻检查的输入统计做小范围修正，不修改小说正文、作者确认、接受历史或写作阶段。

## 问题与变更

- `attributed_dialogue` 按引文在原文中的位置计数。同一句台词在两个位置重复出现，属于两次发言，不能因字符串相同合并；同一处引文同时有前置、后置说话标签，仍只计一次。
- `character_voice_dna.ending_particles` 在句末常见中英文标点及空白之前识别语气词。例如 `走吧。`、`你来吗？` 能分别记入 `吧`、`吗`；句中出现的语气词和只有标点的引文不会凭空产生句尾词。破折号和括号不是本次允许略过的句末字符。
- 新指标使用 `ATTRIBUTION_VERSION = 3`。聚合历史及直接调用 `voice_drift` 都只比较当前版本，避免把 v2 去重后的样本数与 v3 发言次数混用。旧历史保留，不自动迁移；缺少足够同版本样本时不产生口吻漂移判断，可通过原有接受历史重建入口重新分析真实原稿。

重复台词计数修正会影响句长、问句比例和样本门槛，因此必须同步升级版本，不能只修显示结果。

## 使用的 skill 方法

来自用户已安装的 skill 包：

| Skill | 本轮应用 |
| --- | --- |
| `test-driven-development` | 先用同一组原创合成输入复现失败，再修改现有函数并运行回归 |
| `code-reviewer` | 以变更差异为范围核对正确性、输入边界、兼容性及实际调用链 |
| `voice-style` | 参考按人物统计声线、把统计偏离当复读提示而不是自动改稿命令的方法 |

仅使用适合本仓库的方法；没有复制第三方实现、导入整套 skill、改变作品许可证，或为了套用 skill 创建其专属项目结构。保留原有 MIT spaCy span 筛选实现与许可记录。

## 验证

```sh
python -m pytest -q tests/test_voice_metrics_regression.py tests/test_dialogue_attribution.py tests/test_longform_consistency.py
python -m pytest -q
python -m ruff check app.py novel_ai scripts tests --select E9,F63,F7,F82
python scripts/check_current_entry.py
```

新增用例覆盖重复台词、来源顺序、前后标签去重、中英文末尾标点、空白、负例、新旧版本隔离与 `NovelEngine.run` 的最终报告。模型输出使用合成 provider，不发起付费模型调用。

本轮本地结果和基线提交见 [候选记录](../governance/voice_metrics_candidate.json)。远端是否合并及 CI 状态应读取实际 PR 与运行记录，文档不是合并回执。

## 边界

仍是保守的明确姓名/说话标签匹配；不是语义说话人识别，不新增代词、复杂嵌套引号或别名推断。数字与告警不是文学质量评分，也不能证明真实模型输出、真人盲评或市场表现提高。不自动读取或修改私有 Drive 作品，不增加依赖、服务、密钥或部署。

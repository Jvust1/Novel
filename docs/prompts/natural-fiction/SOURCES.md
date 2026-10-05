# 来源、实际复用与边界

核验于 2026-10-01 UTC。通过 GitHub 只读接口读取仓库元数据、当前提交、固定提交的实际 SKILL.md 与 LICENSE，并检查相关完整目录树。星数是本次快照，未来会变化；高星不等于小说效果已经验证。本包没有安装上游工具、运行安装脚本或调用检测服务。

## 采用的两个 MIT 上游

### op7418/Humanizer-zh

- 当次星数：**18,786**，达到 10,000 星偏好
- 固定提交：`f4518a8eab97b8bfebc66a89d34320a89bef6930`（2026-09-23）
- 已读 [SKILL.md](https://github.com/op7418/Humanizer-zh/blob/f4518a8eab97b8bfebc66a89d34320a89bef6930/SKILL.md) 与 [LICENSE](https://github.com/op7418/Humanizer-zh/blob/f4518a8eab97b8bfebc66a89d34320a89bef6930/LICENSE)
- 许可：MIT，Copyright (c) 2026 歸藏；原文保存在 [本地许可证](../../../third_party/prompts/op7418-humanizer-zh/LICENSE)
- 实际复用：编辑约束 3/4、文体与作者声音、工作流程第 3 步中的声音校准、避免词语黑名单、保留通顺段落、避免硬凑句长、逐项语义检查
- 定位：中文文章编辑指导，原库并不是长篇小说专用系统；因此没有直接加载整套分类清单

### blader/humanizer

- 当次星数：**53,203**，达到 10,000 星偏好
- 固定提交：`225a6f39ac85f76ee48dbad772ea4abe4ed6c9d8`（2026-09-28）；该提示 metadata 标示 v3.1.0
- 已读 [SKILL.md](https://github.com/blader/humanizer/blob/225a6f39ac85f76ee48dbad772ea4abe4ed6c9d8/SKILL.md) 与 [LICENSE](https://github.com/blader/humanizer/blob/225a6f39ac85f76ee48dbad772ea4abe4ed6c9d8/LICENSE)
- 许可：MIT，Copyright (c) 2025 Siqi Chen；原文保存在 [本地许可证](../../../third_party/prompts/blader-humanizer/LICENSE)
- 实际复用：Voice 的先读样本、校准句长/用词/标点/起手/转场，以及 How to work 第 3 步的修订后新增/遗漏检查；在中文提示中翻译并收窄为小说局部编辑
- 不采用其针对标点的默认强制规则，也不把其中“虚构任务可创作细节”的例外扩张成任意改写已锁定故事的许可

两个选中仓库在固定提交的完整目录树中均没有 NOTICE 文件。本包新增 [NOTICE.md](../../../third_party/prompts/NOTICE.md) 用于归属说明；不是把新增声明冒充上游文件。分发时保留两份原始版权与许可文本。

## 从上游到本包的实际连接

- `01-writing-before.md`：将两上游的样本声音校准用于写前 STYLE_PROFILE；采用“不能把样本事实搬入新稿”的边界
- `02-editorial-review.md`：直接保留 Humanizer-zh 的“模式是线索、不是黑名单；没有问题可原样保留”规则，改成带原文定位与阅读影响的小说审校
- `03-local-repair.md`：把两上游的新增/遗漏/确定性检查变成逐项事实锁和修订前后核对
- 六条固定来源短摘录见 [source-excerpts.md](../../../third_party/prompts/source-excerpts.md)，精确提交与文件 Git blob SHA 见 [source-lock.json](source-lock.json)

Novel 新写的部分：主/辅类型配置、九类原创微例、视角/叙事距离、人物知识边界与声线、场景状态、物件流转、伏笔时机、允许编辑范围、版本定位、PATCH-ID、相邻段复读与候选稿不自动入 canon。它们是本项目的连接规则，不算上游已有实现，也没有被声称经过上游验证。

以上属于小范围的提示复用和适配，不是只列链接；同样不宣称已把完整上游框架装入应用。没有引入运行时依赖，也不变更项目其他部分的许可。

## 已核验但未复制的原候选

### syw2039/humanizer-zh

- 正确仓库为 [syw2039/humanizer-zh](https://github.com/syw2039/humanizer-zh)，当次 **0 星**，不符合 10,000 星偏好
- 固定提交 `72d73f9c8132817e21f66369de6925a659f9a6a6`
- 已读 [SKILL.md](https://github.com/syw2039/humanizer-zh/blob/72d73f9c8132817e21f66369de6925a659f9a6a6/SKILL.md)、[LICENSE](https://github.com/syw2039/humanizer-zh/blob/72d73f9c8132817e21f66369de6925a659f9a6a6/LICENSE) 和 [NOTICE](https://github.com/syw2039/humanizer-zh/blob/72d73f9c8132817e21f66369de6925a659f9a6a6/NOTICE)，MIT，保留 Siqi Chen 版权并说明基于其 v2.9.1 改编
- 事实保护与中文声音校准方向适用，但所选两源已覆盖，不额外复制近似规则或建立第三份依赖

### 0xtresser/cn-humanizer

- 正确仓库为 [0xtresser/cn-humanizer](https://github.com/0xtresser/cn-humanizer)，当次 **16 星**，不符合 10,000 星偏好
- 固定提交 `59e1e0e759378cd2e02f4089bbbef314d4774b81`
- 已读 [SKILL.md](https://github.com/0xtresser/cn-humanizer/blob/59e1e0e759378cd2e02f4089bbbef314d4774b81/SKILL.md) 与 [README.md](https://github.com/0xtresser/cn-humanizer/blob/59e1e0e759378cd2e02f4089bbbef314d4774b81/README.md)
- README 标为 MIT，但完整固定目录树没有 LICENSE/NOTICE，GitHub API 的 license 为 null；没有取得可原样保留的许可/版权全文，因此本包暂不复制或改编其文字。这是许可核验缺口，不是断言它不能被使用
- 内容还包含无来源统计区间、词语即身份信号的强判断，以及改写示例新增事实的问题；这些不作为小说文风优化依据

## 验证范围

本包已经核对固定来源、短摘录与许可文件的一致性，并检查文档链接与文件结构。它不包含受控读者盲评、不包含全类型完整章稿评测，也不把自评分、删字量或 star 数量当作品质量。接入后应以真实章节的局部前后对照、事实锁复核和作者选择验收。

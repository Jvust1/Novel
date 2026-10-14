# 长篇推进与兼容修复：story-craft 1.2

日期：2026-10-14。基于 `ddd8707d4bf93f3cf8005451646a6775be5976a7` 继续 PR #93；本文是工程记录，不是 main 合并或部署回执。

## 发现与修复

共享流水线虽给起草传入 `recent_summaries`，但 1.1 的初审、复审和修订依据没有这个参数。若调用方没有另把历史拼进 extra_context，编辑阶段会缺少已经提供给写手的近章材料。现在两个编辑依据构造器增加可选 recent_summaries，共享引擎在两处明确传入本轮深拷贝快照，初审/复审复用一致来源。原调用不传新参数仍有效；没有新增模型调用或隐式档案检索。

摘要所有原字段、顺序、版本与冲突均保留，不排序、不合并、不按时间戳选赢家，不从缺失字段推断事实不存在。history_scope 区分未提供、空列表和已提供，明确本构造器不验证接受记录、不读回前章全文。原报告已有的 recent_summaries 输入指纹继续覆盖本轮快照；没有新增存档 Schema 或作者接受规则。此功能不是秘密过滤器或自动历史认证。

新增 `novel_ai/story_progression.py`，通过原四阶段故事常量实际加载：由前章结果改变本章选择；配角与对手回应既有行动；关系、成长、资源和代价跨章积累；区别有意复现与换皮任务；兑现获准推进的承诺，而不无限续订悬念。支线、独立单元、日常、休整和完整结局不自动判错。结构问题仍走原来的重规划路径，不增加自动改纲器。

对话入口的阶段补充见 [05 长篇推进](prompts/natural-fiction/05-longform-progression.md)，提示包 README 已显式链接。四个合成条件见 [progression_cases.json](../benchmarks/story_craft/progression_cases.json)，涵盖信任积累、一次性资源、履行复核约定和已收束主线。它们是测试输入，不是通过的真实生成样本。

## 同时修复上一轮 CI 回归

本轮读取上轮 run `38521853529` 的 Ubuntu/Python 3.11 job `115713134835` 日志，记录为 **1 failed, 2413 passed, 9 skipped**。失败是既有 `tests/test_routed_engine_port.py::test_routed_run_splits_writer_and_reviewer_and_passes_context`：旧路由调用传 bible=None，1.1 新增的 `genre_craft_rules(bible.genre, ...)` 触发 AttributeError。查询时整个矩阵仍有 Windows 任务运行，不能将上轮视为成功。

没有删除、跳过或放宽该原有测试。三个提示工厂仅在 bible 为 None 时不给类型提示，原用户资料仍序列化为 null，不凭空构造故事设定。正常类型继续按原规则选择；其他非法类型不被悄悄吞掉。规划、起草和审校的同一问题都已覆盖。

本地先对未修复的原 prompts 执行新增回归用例，实际得到 **4 failed, 10 passed**，复现 None 的 AttributeError；补丁后同一组 **14 passed**。这证明具体提示工厂回归得到修复，不等于原整套路由/CI 测试已经重跑通过。

## 本轮实际验证

```sh
python -m pytest -q tests/test_story_progression.py tests/test_missing_bible_craft.py tests/test_editorial_context.py
```

**72 passed**：44 项历史传递、边界与阶段规则检查；14 项空设定回归和实际提示工厂检查；14 项未修改的既有编辑依据测试。新增 Python 源码与测试通过 compileall。记忆抽取和参考分析提示没有加入长篇创作规则。

新增 `tests/test_story_progression_engine.py` 含参数化后 **8 项**实际共享引擎用例，使用离线脚本 provider，覆盖同写手/独立 reviewer、Bible 有/无、初审/修订/复审同源、结构问题仍暂停修订、跳过审校、空历史和调用方后续改动。**这 8 项和全仓库测试未在本地执行，须看当前新提交 CI**。未用诊断替身把这组测试记为本地通过。

当前环境通过连接器读取源码，网络克隆因 DNS 失败不可用。为本地验证重建的修改前 engine.py、prompts.py、story_craft.py、editorial_context.py、提示包 README，以及未修改的 models.py、story_craft_profiles.py 和 test_editorial_context.py，均实际计算 Git blob SHA 并核对与读取来源一致。未修改文件仅用于本地测试，不重复提交。Git blob SHA 不冒充档案 SHA-256 或作者接受证据。

## 质量、成本与使用边界

本轮未读取真实小说、私有档案或参考书，未执行付费模型、真实章稿 A/B 或真人盲评。没有程序自动识别所有平淡问题；测试只验证代码与提示契约，不量化文学质量。

无新增依赖、服务、部署或默认调用轮次。阶段提示和传给编辑的近章摘要增加输入长度；不声称零 token/费用影响，也未测量具体 provider 的上下文余量。调用方应使用本次相关且已核对的历史，而不是自动加载全书。

现有计划、正文和记忆不会自动改写；结构改动仍须确认具体计划版本。是否合入 main、当前 CI 状态以真实 ref 和运行回执为准。回退本轮提交即可撤销本轮变更，无存档迁移。机器记录见 [story_craft_progression.json](../governance/story_craft_progression.json)。

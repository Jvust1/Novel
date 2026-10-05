# 作者改设定以后继续写下一章

这条候选补上 [作者变更协议](GPT_AUTHOR_AMENDMENTS.md) 与 [实际档案续写](ACCEPTED_ARCHIVE_CONTINUATION.md) 之间的连接。作者修改设定或文风、完成影响复审并保存读回后，可以重新确认本章计划，再沿用已有预算会话起草、审校、局部修订和复审。缺少当前读回或仍有未决影响时，发送前停止。

日常入口仍是 GPT 对话，不要求作者本地安装或新建服务。GitHub 插件能读文件不代表已执行 Python。只有当前确有可信执行器时，才运行以下自动检查；否则按原协议读取私有原件、逐项核对并如实说明程序检查未运行。

## 变更和接受顺序继续由作者决定

1. 作者提出具体设定或文风的旧值、新值和理由
2. 作者确认这份变更；原计划和候选保留，当前旧确认失效
3. 复审受影响的已接受章节和派生资料；有冲突就停在待对账，不能把问题改成兼容来通过
4. 作者确认恢复，真正保存并读回当前日志
5. 重新制定和确认当前版本的章计划，再生成待审正文
6. 正文接受、记忆确认和最终保存仍走日志已有固定动作；一次模型成功不会自动新增接受记录

新接口只读取、重放已存在的历史，并生成候选。它不会接受变更、补造确认、追加新事件、修改正式记忆或替作者修订历史章。

## 日志继续拥有状态

新 `RestoredJournalSource` 与普通 v1 `RestoredSource` 分开。恢复日志必须明确核对故事 ID、已接受章节 revision、设定上下文 revision、当前日志指纹，以及真实文件 SHA-256。作者撤回一次文风变化后，旧的历史内容指纹可能再次相同；日志版本和来源文件身份仍不同，旧执行结果不会因此恢复有效。

`restore_journal_source` 实际读取文件，调用原 `load_journal` 检查保存回执和事件链，然后由日志自己的新历史/预检接口检查当前真实读回。复制 JSON 中的 `verified` 字段、重放出一个投影、序列化再导入对象，都不能替代 `load_journal` 产生的本次观察。

返回的故事投影仍带 `journal_owner`。普通 v1 保存、状态更新和预检继续拒绝直接使用它；没有删除归属字段、伪造 v1 保存/读回回执或进行隐式迁移。已有 v1 入口的历史指纹、首章行为和默认上下文输出保持不变。

## 实际复用哪些代码

- 日志自己的接口验证真实观察、当前日志/上下文版本、变更状态和影响复审，再使用原有历史推导与上下文格式化
- 普通档案和日志只共享纯计算部分，各自的所有权与读回门禁仍在各自入口；没有第二套历史缓存
- eventsourcing 已许可内核实际参与每次日志重放，检查事件身份、顺序和精确下一版本
- #54 的每次请求前/响应后来源检查与 #52 的同一预算账本继续使用，格式降级也不能漏计或漏查
- 当前章计划、完整文风、必要设定和人物知识继续进入现有 `run_from_plan`；结果依然需要作者明确接受

来源与完整许可证见 [本轮复用记录](upstream/journal-continuation-2026-10-01.md)。

## 执行器调用

```python
from novel_ai.accepted_writing import restore_journal_source

source = restore_journal_source(
    actual_local_journal,
    expected_story_id=actual_story_id,
    expected_revision=actual_story_revision,
    expected_context_revision=actual_context_revision,
    expected_journal_sha256=actual_journal_sha256,
    expected_file_sha256=actual_file_sha256,
)
result = existing_budgeted_session.run_from_accepted_archive(
    source,
    current_chapter_id=actual_current_chapter_id,
    required_chapter_ids=required_accepted_chapter_ids,
    review=True,
    auto_repair=True,
)
candidate_text = result.final_text
source_and_budget_evidence = result.report()
```

所有变量都须来自本次真实读取和已授权的执行环境。日志指纹可由原 `scripts/story_journal.py inspect` 在实际执行器中取得；文件 SHA-256 必须真算，不能用 Drive 文件 ID 或 Git blob SHA 冒充。

原 `restore_source` 仍专用于未被日志拥有的 v1 档案，误传日志继续报错。新接口是明确选择的补充入口；首章仍用现有首章流程，有至少一章接受历史后才使用这里的续写检查。

## 恢复与验证边界

每个 HTTP 尝试发送前、响应正文读取后，以及返回正文或来源报告时，都重新读取并核对同一日志。中途出现新候选、新变更、不同上下文、文件替换、截断或冲突事件时，旧句柄作废，保留现有材料并重新恢复。它不自动跳过需要确认或复审的阶段。

采用的是日志内嵌原件和已接受快照。外部原件链接不会被自动跟随，也不证明远端 Drive 文件已经是最新。日志仍须按原协议完整有序重放；没有百万字性能、分页归档、多设备锁、远端事务或恶意进程沙箱证明。预检查仍有 64 MiB 文件支持上限。

现有历史结构统计来自已接受计划，人物口吻统计来自可明确归属的对白，不能代替正文事件完整提取或真人文学评估。测试是原创合成故事与明确标识的模拟确认，没有付费模型或真实作者接受。最终工程证据见 [候选记录](../governance/journal_continuation_candidate.json) 和对应提交 CI。

# 作者日志续写的实际复用

本次复用已有日志、历史推导和受预算约束的请求流程，修补“作者改设定后，日志不能进入实际受控续写”的连接缺口。没有新增外部框架、数据库或依赖，也不把既有上游重复算作新搬入项目。

主要实际来源是 [pyeventsourcing/eventsourcing](https://github.com/pyeventsourcing/eventsourcing)，2026-10-01 16:30 UTC 核实 **1,687 星**、BSD-3-Clause。精确提交 `575d42c10a821828639b90178ed56703abe9c9f1`，版本 9.5.5。其不可变事件/聚合、有序 projector 和身份/下一版本检查的既有选择性源码提取，经 `gpt_story_journal._project_journal` 实际参与本次每个日志恢复、历史推导和写作来源检查。

原完整许可证、64 行源示例、精确方法片段、改动说明和哈希都保留于 [NOTICE](../../third_party/eventsourcing/NOTICE.md) 与 provenance.json。本轮重新核对了其中 5 个许可/源示例/片段/运行移植文件的 SHA-256，全部与原固定版本记录一致。没有启用完整 eventsourcing SDK、动态导入主题、数据库快照或自动迁移。

同时继续运行已有 Pydantic 严格数据验证、pytransitions 原章节状态重放，以及 PydanticAI 选择性用量判断。日志归属、实际读回、作者确认和领域冲突仍是 Novel 的责任，不把第三方重放能力误称为身份认证或防伪签名。

调用链是 `restore_journal_source` → `load_journal` → 日志自己的 `rebuild_journal_accepted_history` / `preflight_journal_next_chapter_context` → 共享纯历史/上下文函数 → 原 `BudgetedWritingSession.run_from_accepted_archive`。每次真实 HTTP 尝试仍使用同一份预算和来源检查。

独立测试还固定了 #54 原 v1 历史/预检输出的基准摘要，证明抽取纯函数没有静默改变旧历史身份、首章特殊分支或当前草稿默认行为。新测试检查日志假回执、缺失影响审校、上下文撤回、事件冲突、请求中改稿和明确确认后的实际续写。工程通过不等于文学质量或市场效果通过。

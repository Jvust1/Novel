# 已接受档案续写：实际复用与来源

本轮把已有模块连成来源读回 → 历史重建 → 受预算约束的正文/审校/修订/复审。没有新增外部框架或依赖，不把原有依赖重复计为新搬入项目。

| 来源 | 当前核实与许可 | 本轮实际运行位置 |
|---|---|---|
| [Pydantic](https://github.com/pydantic/pydantic) | 2026-10-01 16:08 UTC，28,917 星；MIT；已运行版本 2.13.5，提交 `001dea020e0809844e5b17666432c9135a976f46` | StoryState / AcceptedChapter / Artifact 的既有严格验证，以及新入口的 ChapterPlan、场景及原生人物字段严格投影 |
| [PydanticAI](https://github.com/pydantic/pydantic-ai) | 同时核实 20,322 星；MIT；已有选择性源码移植提交 `675d9f52b38e4dffe0c248451b5fb44595f7308c` | #52 RequestBudget.admit 的实际请求数和预留输出上限判断，现被每个档案续写 HTTP 尝试调用，含格式降级 |

Pydantic 完整许可及已核对安装文件来源在 [原 NOTICE](../../third_party/pydantic-vector-validation/NOTICE.md)。PydanticAI 的完整原始 usage.py、MIT LICENSE、精确 blob/SHA256 与删改说明在 [原 NOTICE](../../third_party/pydantic-ai-usage-limits/NOTICE.md)。这些文件原样保留；完整 PydanticAI SDK 没有安装或宣称接入。

Novel 内部复用包括 #51 的历史指纹和 next-preflight、#52 的实际 HTTP 账本、#50 的封存最终文本/审校报告，以及原有共享 run_from_plan。提前保留的未发布历史候选贡献了实际来源重读、严格计划适配、完整文风卡和返回证据的实现方法；没有照搬其另一套派生缓存或改变 journal 所有权。

直接入口为 `BudgetedWritingSession.run_from_accepted_archive`，来源检查为 `novel_ai/accepted_writing.py`，HTTP 降级内部检查为 `OpenAICompatibleProvider.guarded`。新增测试真实通过 HTTPX MockTransport 记录发送的完整请求，核对预算账本与来源变化时没有多发下一请求。星数和源码复用不构成文学质量证据。

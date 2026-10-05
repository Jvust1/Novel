# 记忆确认链路的实际开源复用

本轮以现有成熟组件补齐实际“提取候选→作者确认→固定提交→恢复”路径，不新建第二个权威故事数据库，不把已有依赖重新算成新增搬运数量。

## 执行位置与精确来源

- pytransitions/transitions：2026-10-01 再核实 6,596 星，MIT。原有完整、未修改的 core 模块为 0.9.4，提交 `bd42b38f3627e6bca7274fb4d9af2e105f75da7c`。`memory_proposals.apply_memory_proposal` 实际使用 Machine、auto_transitions=False，执行 candidate→chapter_accepted→confirmed 后才调用固定提交。没有从 JSON 载入回调、动态模块或任意状态机。完整源/许可与 Git blob 对照沿用 third_party/transitions
- mahmoud/boltons：再核实 6,932 星，固定提交 `4e5faa3d7e4008d89e0d8bf1ea87b6d9a061a16d`。GitHub 许可元数据为 NOASSERTION，实际完整 BSD 风格三条款已保留。`save_memory_proposal` 与 `memory_commit` 经 ProjectStore._write 进入原有 AtomicSaver/atomic_save 源码移植；完整原件、修改记录、许可沿用 third_party/boltons
- pydantic/pydantic：再核实 28,915 星，MIT。运行版本 2.13.5，固定源码提交 `001dea020e0809844e5b17666432c9135a976f46`。MemoryExtraction 与子记录用 extra=forbid、伏笔状态用明确 Literal；原始作者扩展字段在快照/合并时保留，不能靠忽略未知模型字段制造“成功”。没有重新实现一套类型系统，许可和来源沿用 third_party/pydantic-vector-validation
- #52 已引入的 PydanticAI 请求/输出额度检查源代码小段：在新的真实工作台提取入口执行完整输入/次数/预留额度检查。它仍是原 selective port，不是又装了一套 PydanticAI。精确 pin/完整许可/源码见 third_party/pydantic-ai-usage-limits

## 为什么继续使用固定意图而非新增缓存框架

先核对了现有 ProjectStore 的已测试 extraction/summary 二文件恢复机制。它不能覆盖旧 app 中另外七份文件，因此本轮扩成一个独立、固定 allowlist 的已确认操作；没有把原来二文件通过当成九文件事务已经成立。

此前同日检查过 grantjenks/python-diskcache（2,911 星，提交 `ebfa37cd99d7ef716ec452ad8af4b4276a8e2233`，实际 LICENSE 为 Apache-2.0）的 SQLite 缓存事务。引入它仍不能让既有 JSON 文件读者自动拥有统一权威源、作者接受和完整版本绑定，还会增加第二套存储。此次未安装/复制它，也未计为已融合。新内存结构、固定意图验证、恢复与 UI 接线是 Novel 必需的领域逻辑。

真实复用验收点不是库数量：模型不能自动写 Canon；同一组已确认 after-images 才能恢复；换来源会拒绝；重试不重算增量；作者新资料不被旧回执覆盖。星数和测试数都不证明文学质量。

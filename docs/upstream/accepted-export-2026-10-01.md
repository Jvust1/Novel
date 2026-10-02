# 接受稿导出的真实复用

本轮连接已有接受档案/作者日志和已有审阅包，不新增框架或依赖，不把已有上游算作新搬入项目。

- [Pydantic](https://github.com/pydantic/pydantic)：2026-10-01 17:40 UTC 通过 GitHub 插件核实 28,918 星，MIT；已运行 2.13.5，对应精确提交 `001dea020e0809844e5b17666432c9135a976f46`。既有 StoryState/AcceptedChapter 严格验证与本轮 MarketProfile/MarketScore 重新验证实际运行。完整许可证与来源保留在 [NOTICE](../../third_party/pydantic-vector-validation/NOTICE.md)
- [pyeventsourcing/eventsourcing](https://github.com/pyeventsourcing/eventsourcing)：同时核实 1,687 星，BSD-3-Clause；固定 9.5.5 提交 `575d42c10a821828639b90178ed56703abe9c9f1`。既有选择性源码移植通过 `load_journal` / `_project_journal` 实际重放日志，守住归属、事件顺序与版本，再进入 `rebuild_journal_accepted_history`。原许可、示例、片段、运行移植和哈希见 [NOTICE](../../third_party/eventsourcing/NOTICE.md) 与 provenance.json

项目内部实际复用 #51 原生接受历史身份、#56 实际读回来源、早期 MarketCorpus/ReleasePack 十维审阅及 ZIP、#45/#48 沿用的原子排他发布路径。本轮没有调用 PydanticAI 请求预算、boltons 文件替换或新缓存，不能把它们重复计为本次导出运行的新增来源。

实际路径：`restore_source` / `restore_journal_source` → `_fresh` → 原生已接受历史重建 → MarketCorpus → 原 build_release_pack/release_bundle_bytes → 接受来源清单 → 原 save_release_bundle（增加来源边界回调及暂存检查）。独立旧 ZIP 黄金摘要与新来源对抗用例共同证明真实连接；不是拷入未使用仓库或仅列推荐清单。

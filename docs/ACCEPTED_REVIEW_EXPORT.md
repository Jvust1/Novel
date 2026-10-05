# 从已接受版本整理私有审阅包

## 给作者的用法

在 GPT 里可以说：“读取当前私有故事档案，把我已接受的第 1、3、2 章按这个顺序整理为三章审阅包。使用我提供的书名、简介和读者定位，保留正文原样，未接受稿不收进去。”

GPT 先核对实际分支、作品和版本，说明选中的章节及顺序。GitHub 文件访问不等于执行代码：只有会话有实际 Python 执行器、已取得私有档案原件时，才使用下述程序。没有执行器时按 [对话协议](GPT_WRITING_ENTRY.md) 准备内容，如实标注 ZIP 和程序校验未运行，不要求作者本地安装。

## 实际连接的能力

`novel_ai/accepted_export.py` 将真实读回的 `RestoredSource` 或 `RestoredJournalSource` 接到现有 `MarketCorpus` → `build_release_pack` → `release_bundle_bytes` → `save_release_bundle`。这次新增的是接受档案适配与跨保存边界检查，复用已有 3 章开篇 / 20 章留存审阅方式、十维真人评分、确定性 ZIP 和不覆盖原件的保存器。

- 显式 `chapter_ids` 必须唯一且恰好 3 或 20 个，可以是明确子集或非自然顺序；程序不猜叙事顺序
- 正文只取档案内 `AcceptedChapter.draft.text`，保留 UTF-8、BOM、CRLF、首尾空白。被拒绝的 A 稿、当前未接受候选和旧磁盘正文不进入包
- 日志必须真实加载、身份和版本吻合、没有未决变更且所有影响复审已完成。不能把日志投影冒充普通 v1 档案
- 生成、取出字节、保存、已有文件复用、竞争复用以及最终读回均验证当前来源。来源改变后旧句柄失效；重新实际恢复后才能再导出
- 导出不执行作者接受、记忆应用、恢复事务或模型调用，也不改 Canon、作者日志或故事进度

## 输出与身份

ZIP 复用现有 `chapters/001.md` 等正文、`release_pack.json`、`market_scoring.csv`、`manifest.json` 和说明，增加 `accepted_source.json`。清单记载故事版本、实际源文件/状态摘要、原生已接受历史摘要、所选章节顺序、计划/正文版本与来源指纹、接受记录摘要和记忆更新 ID；日志另附原生日志摘要与上下文版本。主清单绑定接受来源清单的实际文件 SHA-256。

不会自动加入完整 Canon、文风卡、计划原文、未选正文、来源路径或作者确认聊天原文。书名、简介、受众、标签、评分备注以及故事/章节/记忆标识仍是明文输入；允许字段不是隐私净化器，作者主动写入的内容会保留，分享前须按接收者核对。包默认私有，不能因本仓库公开而公开真实作品。

同一来源文件、元数据和选择顺序生成相同字节，换下载目录也不改变包身份；实际执行句柄仍绑定自己的路径。同文不同接受证据、不同故事版本或不同顺序会生成不同来源证明。文件哈希只能反映实际观察到的字节，不能认证真人、验证档案外原件是否最新，或发现未记录且恢复成相同字节的瞬时变更。

## 可选执行入口

脚本 `scripts/export_accepted_review.py` 接受源文件、另行准备的元数据 JSON，以及明确的作品、版本、源 SHA-256、阶段和有序章节参数。真实计算 SHA-256 后再填写，不能从 Git blob SHA 或推测得出。

```bash
python scripts/export_accepted_review.py private-story.json release-copy.json \
  --story-id synthetic-story --revision 3 --sha256 ACTUAL_FILE_SHA256 \
  --stage opening_3 --chapter-id ch-1 --chapter-id ch-3 --chapter-id ch-2 \
  --out-root private-output
```

作者日志还需 `--source-kind journal --context-revision N --journal-sha256 ACTUAL_JOURNAL_SHA256`。普通 v1 入口拒绝偷偷附上日志身份，日志入口拒绝缺失日志身份。元数据白名单为 `profile/title/one_line_hook/short_blurb/long_blurb/tags/content_warnings/manual_checks`，前四项必需，`profile` 也拒绝未知字段。示例需根据真实原件替换，不可直接作为已完成回执。

Python API 可用 `preview_accepted_corpus` 生成独立评分预览，再向 `build_accepted_review_bundle` 提供符合原有项目/阶段/全文与顺序/读者/类型摘要的完整 `MarketScore` 记录。不提供评分时 `human_review_status=awaiting_human_review`；提供合格记录时只表示已记录评分，`publishability_verdict` 始终为空。程序不认证评分者身份，不把正文接受当作真人盲评。

## 保存与失败边界

保存到规范故事 ID 的 `projects/<story>/exports/release-<ZIP SHA256>.zip`。临时文件完整写入并 fsync 后，检查根目录祖先、目标、暂存文件身份和实际字节，再用同目录排他硬链接发布。目标已存在时只有逐字节相同且当前来源再次通过才能复用，不覆盖不同内容。

中断可能留下旧的完整文件或新的完整文件；发布后的来源变化、读回或清理失败都按失败报告，但可能已经存在完整产物。不得删掉该完整文件、声称自动回滚或报告部分章节成功。重新加载来源并实际读回核对后才可确认结果。检测到根目录跳转或外部临时文件替换时不追随、不删除别人的文件；不可达的暂存文件可能保留供人工检查。

这是可信本地/合作进程的边界核对，不是任意恶意进程竞争下的隔离、目录 fsync 持久性保证或 Drive 多文件事务。没有自动上传、投稿或扩大分享权限。

## 验证与尚未完成

原创合成夹具实际走计划、正文、作者确认、记忆确认、保存和恢复，覆盖 v1 与作者日志；检查拒绝 A / 接受 B、20 章与任意子集顺序、接受证据差异、精确 UTF-8、旧来源、伪造句柄、待复审日志、竞争复用、失败重试和两个真实 CLI 入口。独立测试固定旧打包器四种 ZIP 的字节摘要，防止悄悄改变既有输出。

见 [工程证据](../governance/accepted_export_candidate.json) 和 [实际复用](upstream/accepted-export-2026-10-01.md)。这不证明真人文学质量、签约或投稿合规；尚不提供整本书任意章数排版、历史章改写自动迁移、外部原稿同步或自动出版。

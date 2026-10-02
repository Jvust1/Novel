# 读回已接受档案后，安全写下一章

本候选补上的是一次真实调用链：作者已确认本章计划，执行器实际读回指定故事档案，从已接受历史重建前情，然后用同一份资料写正文、审校、局部修订和复审。任何一次请求前后发现档案变化，就停止返回可继续使用的结果；模型返回的正文始终是待作者接受的候选。

主入口仍是 [GPT 对话写作](GPT_WRITING_ENTRY.md)，无需作者安装程序。GitHub 插件只读文件时，按该文本协议读原件、确认版本和人工审读；不能说已运行下面的 Python 检查。下面是已有可信执行器的可选接口，不新增服务、凭据或付费调用。

## 采用现有机制，补齐中间连接

- 保留 #51 的 `rebuild_accepted_history` / `preflight_next_chapter_context` 和已有历史指纹含义；不引入第二套缓存
- 将 `accepted_chapters` 的口吻历史与已解析计划结构实际送入原有 `NovelEngine.run_from_plan`
- 沿用 #52 `BudgetedWritingSession` 的同一个预算：正文、审校、修订、复审，以及格式降级的第二次 HTTP 请求全部计入；失败或重复调用不重置额度
- 保留 #53 的独立记忆候选确认/提交协议；这里不写 Canon、不推进故事状态、不自动接受正文或记忆
- 完整文风卡、人物自定义字段与必要 Canon 留在预检上下文。原生模型字段另作严格投影，未知的当前计划字段会拒绝而非静默丢弃

## 权威来源与中断边界

`restore_source` 必须获得明确的本地文件、故事 ID、故事 revision 和实际计算的文件 SHA-256。它真正读取、验证保存回执、建立本次读回，并在恢复结束前再次核对文件。随后每次使用来源、每个 HTTP 请求发送前、每个响应正文读取后，以及访问最终结果时都重新读取核对。

历史指纹与执行来源绑定是两回事：保存新的未接受候选可以保持 #51 的历史指纹不变，但文件字节已经变化，因此旧执行句柄必须作废。重新读回后按新阶段决定下一步，不能用旧结果给新档案盖章。

确认对象只绑定调用者提供的版本/内容证据，不认证真人身份。GPT 仍须先核对作者真实指令。审校通过、模型输出成功和文件保存都不等于接受。

只使用档案内嵌的已接受快照，`Artifact.location` 不会触发联网或任意文件读取。未声称已检查外部 Drive 原件是否又被改动；需要这种保证时，先用已授权工具重新获取并对账。

原 `restore_source` 接入已有至少一章接受历史、未被 journal 拥有的 v1 档案。首章继续走现有对话写作或 run_from_plan；这里不改变 #51 两种空历史指纹的既有定义。作者日志可显式选择 [restore_journal_source 入口](JOURNAL_CONTINUATION.md)，按日志自己的读回/影响复审门禁进入同一预算会话；不能把带 `journal_owner` 的投影当成普通 v1 输入。已接受旧章重写仍须另行对账。

## 上下文与实际额度

本章必须处于 `ready_to_draft`，并持有当前具体版本的计划确认。当前计划需要完整、非空的原生 ChapterPlan JSON，或者仅含 `chapter_plan` 的包装；场景因果字段不能为空，编号必须是严格正整数且不重复。不调用模型补造缺失字段。

下一章资料来自 #51 预检。当前未接受草稿显式排除，但保留在原档案中；既有预检默认行为不变。仅能按已接受章节 ID 选择 Recall，必需来源整体保留，可选原件整体省略；不能悄悄截断知识边界。来源身份页脚先预留额度，避免最后附加时挤掉必要信息。

预检额度是 UTF-8 字节数，实际 HTTP 的完整 JSON 请求另由 #52 的每次/累计字节数、调用次数和预留输出 token 上限约束。它不是 ChatGPT Pro 订阅额度、精确输入 tokenizer、真实账单或跨设备锁。历史未解析计划会显式列出，不伪称已完成正文事件抽取或文学判断。

## 执行器调用

```python
from novel_ai.accepted_writing import restore_source
from novel_ai.budgeted_writing import BudgetedWritingSession

source = restore_source(
    actual_local_archive,
    expected_story_id=actual_story_id,
    expected_revision=actual_revision,
    expected_sha256=actual_file_sha256,
)
session = BudgetedWritingSession(already_authorized_explicit_router_config)
result = session.run_from_accepted_archive(
    source,
    current_chapter_id=actual_current_chapter_id,
    recall_chapter_ids=chosen_accepted_chapter_ids,
    required_chapter_ids=required_accepted_chapter_ids,
    budget_bytes=120000,
    review=True,
    auto_repair=True,
)
# 下列访问仍重新核对实际档案和结果证据；不应用记忆。
candidate_text = result.final_text
source_and_budget_evidence = result.report()
```

这些变量是调用者必须真实提供的输入，不是已经存在的用户故事、端点或授权。无需模型的 `prepare_accepted_context(source, current_chapter_id=...)` 可先预览资料及预算；它包含私有上下文，只返回给调用者，不应自动写进公共日志或仓库。

已有 `run` / `run_from_plan` 保持兼容；这条额外入口不允许调用者注入不计数的 provider、结构化 SDK 或外部审校 Hook。

## 已验证与仍未验证

验证使用原创合成故事、明确标识的模拟确认及 HTTPX MockTransport，检查来源变化、格式降级、重复/失败调用、预算不足、换计划保留旧稿、严格计划投影和结果篡改。没有调用真实付费模型或替作者接受实际作品。

适用边界是可信本地目录和合作写入者。档案预检查上限为 64 MiB，既有 loader 随后会再次读取；不是恶意进程的内存沙箱或跨文件事务，也无法观察远端 Drive 上未同步到本地的改动。还没有真实数十万字创作压力、独立真人文学盲评、Windows 全面验证或全量安全扫描证据。

来源与许可证：[实际复用记录](upstream/accepted-archive-continuation-2026-10-01.md)。最终测试/发布状态以本候选的 [工程记录](../governance/accepted_archive_candidate.json) 与对应提交 CI 为准，不把旧主分支或旧交接页的历史状态当作当前验收。

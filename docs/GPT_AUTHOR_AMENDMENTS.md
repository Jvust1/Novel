# 作者改设定、改文风后，如何安全继续

本页接在 [GPT 写作入口](GPT_WRITING_ENTRY.md) 的版本确认与保存步骤后。作者仍在 GPT 对话中操作；GitHub 插件提供规则与文件访问，不自动执行 Python。真实小说与变更档案只进作者指定的私有 Drive。下面的程序检查只有实际运行后才能报告通过。

## 1. 这次解决什么

写到一半，作者可能要求“改成更贴近主角的视角”“调整世界规则”“换一份章纲”。不能只改文风卡后沿用旧稿的“已确认”。新的可选档案把旧记录保留下来，先查影响，再继续写：

1. 记录变更提案：具体字段的旧值、新值、理由。提案还不是正式设定
2. 作者明确确认该提案和目标版本，才把新设定/文风用于当前状态
3. 保留旧计划、草稿及接受证据；未完成的旧计划/草稿转入历史，当前确认失效
4. 默认列出全部已接受章节，以及当前 Active/Recall 摘要、知识、伏笔、来源索引，逐项复审
5. 作者确认完整复审结果后，保存新档案并实际读回，再重新确认计划、起草或续写

这是保守的全量影响清单，不是自动理解情节依赖的智能分析器。程序能防止漏掉清单条目，不能证明审读结论正确。

## 2. 对话模式，无执行器也可用

GPT 先读当前私有档案与变更前原件，给作者看一份短变更单：改什么、旧值/新值、哪些章与派生记忆需要复核、哪些未完成稿件会失效。不要用“继续”“整理一下”冒充接受变更。

作者确认后，为这次变更分配独立 `context_revision`，保留旧档案版本。每条复审记录至少包含：目标章节或派生记忆、实际读到的来源/版本、变更版本、问题定位和结论。没有算过哈希就留空，不填想象的值；没有运行程序就标为人工对话核对。

“兼容”表示现有文字仍可保留；不是悄悄改了正文。若发现必须改旧章或重算记忆，停在“待修订/对账”，先处理作者明确选择的范围。不要把问题改成已解决来通过检查。完成后展示简短差异与复审结果，等作者确认恢复，再真实保存、读回。换聊天时重新读取这些原件和未决清单。

## 3. 可执行档案与原格式的关系

实现：[`gpt_story_journal.py`](../novel_ai/gpt_story_journal.py)，命令行：[`story_journal.py`](../scripts/story_journal.py)。

新封套格式 `gpt-author-journal-v1` 包含原 v1 JSON 的**完整文本字节、来源身份与指纹、明确迁移确认**，以及有序追加的事件。旧 `gpt-state-checks-v1` 文件不原位升级、不被删除；迁移应写到新的私有文件。已有 v1 程序与序列化默认字段保持兼容。

三种版本分开：

- `story.revision`：已接受章节数，继续遵守原 v1 不变量
- `context_revision`：作者接受设定/文风变更的次数，不假造章节来递增
- 事件 `originator_version`：本封套的严格连续序号

当前投影由迁移原件和事件重放得到，不信任另存的“最新状态”。公开返回的故事投影带所属封套标记，旧 v1 写入/预检接口拒绝直接使用它，避免正常调用时绕过影响复审。手工删除标记、重写整个档案和所有哈希属于脱离协议的伪造；这里没有防篡改签名、身份认证或授权服务。

## 4. 实际复用的上游代码

直接调用 BSD-3-Clause 许可的 [eventsourcing 源码提取](../third_party/eventsourcing/NOTICE.md)：冻结 Pydantic 事件/聚合模型、有序重放闭包，以及故事身份和精确下一版本校验。2026-10-01 核实 1,687 星，固定提交 `575d42c10a821828639b90178ed56703abe9c9f1`。完整原示例、精确片段、许可证、变更说明和哈希均保留。

这个内核实际参与每次日志验证和当前状态恢复；原有章节写作仍调用既有 Pydantic + pytransitions 流程。没有新增数据库、模型、网络、后台任务或服务，也没有复制一个用不到的完整仓库。SQLAlchemy 的真实历史表与旧会话冲突方案经过比较，但不适合本次私有 JSON/Drive 入口，未引入。

## 5. 支持的变更范围与明确限制

可替换以下完整字段：`canon.story_bible / world_rules / locked_facts / outline / characters` 和 `style_profile`。须提交精确旧值；未知路径、重复路径、空变更或字段类型错误会拒绝。

不能借此修改已接受章节、接受记录、已应用记忆、操作历史、读者揭示账本、保存回执，或任意 JSON 路径。Active/Recall 目前只纳入必须复审的派生资料，不能用这条窄接口直接改写。

本轮没有实现历史正文替换、分支合并或历史记忆重算。复审发现必须修改旧正文/派生记忆时会阻塞。未接受提案可取消；已接受变更不能删除。若已出现 `requires_revision`，本接口只允许再提出**精确回到该变更前上下文**的反向提案，经过新的确认/复审恢复；不能再改一个无关文风字段来洗掉问题。历史变更和问题始终保留。

当前实现每次验证完整重放，日志含必要文本和原件；没有宣称百万字日志的性能、分页归档或多设备事务已完成。导入老档案缺原件/历史时仍拒绝，不捏造证据补齐。

## 6. 程序接口与确认绑定

- `migrate_state(origin, confirmation)`：明确新建封套；origin 是实际读取的原 JSON artifact
- `project_journal / owned_story`：只读诊断投影，不代表保存或本次读回
- `transition_journal(journal, command)`：固定动作的复制后更新，不改变调用方输入
- `confirmation_binding(journal, scope)`：只返回需要绑定的字段，不生成作者确认
- `save_journal / load_journal`：真实单文件保存/读取
- `preflight_journal`：既检查完整上下文预算，也检查待确认、待复审和待实际读回

命令包含 `story_id / action / operation_id / expected_journal_sha256 / payload`。动作是 `story / propose_amendment / cancel_amendment / accept_amendment / review_impact / resume_reconciled`。`story` 包装原有固定章节动作，不从文本导入命令或回调。

变更确认绑定提案 ID、上下文版本、目标上下文指纹；恢复确认再绑定完整复审结果指纹。普通计划/正文/记忆接受仍须原 v1 的来源指纹与版本，同时增加上下文绑定。迁移、变更、恢复及原章节确认都需要真实作者指令；测试中的 `synthetic-test://...` 只是假作者测试夹具，不得复制为真实确认。

所有已接受历史仍原样保留。活跃计划/正文的计数器不回到 1；相同文字重新加入也须新版本确认。完全相同的操作重试不追加事件；同 ID 改输入、旧基础、跨故事、断序、重复事件和父指纹冲突均拒绝。

## 7. 保存、中断、读回

新文件以原子不覆盖方式发布；已有文件必须提供上次实际读取的完整文件 SHA-256，并保留原迁移证据和整个已保存事件前缀。临时文件私有、目标/祖先符号链接拒绝。写入前后再次核对旧字节，仍要求调用方串行化写入；没有通用并发锁或 Drive 事务保证。

纯重放不会把阶段自动变成“已读回”。接受变更后，即使复审完成，所有继续写作与预检仍需当前封套的真实保存/读取。成功 `load_journal` 产生只在内存中有效的读回凭据；把旧回执字段复制到 JSON 再导入不会获得本次读取资格。历史事件可以保留当时的检查点证据，用于确定性重放，不声称现在又读了一遍。

写入返回前中断时先读回当前文件；完全相同操作可安全重试。截断 JSON 无法验证；完整但较旧的有效档案只有结合调用者保留的最新文件哈希/版本才能识别回退。任何系统都不能只看一个孤立旧副本，就知道外面是否还有更新版本。

## 8. 实际执行示例

以下仅供当前确有 Python 执行器的 GPT 使用，不要求作者本地安装。先准备作者实际确认 JSON；命令不会补填接受决定。

```bash
python scripts/story_journal.py migrate /private/story-v1.json /private/story-journal.json --source-id story-state --source-revision 7 --confirmation /private/author-migration.json
python scripts/story_journal.py inspect /private/story-journal.json --story-id stable-book-id
python scripts/story_journal.py apply /private/story-journal.json /private/explicit-command.json
python scripts/story_journal.py inspect /private/story-journal.json --story-id stable-book-id --binding amendment
python scripts/story_journal.py preflight /private/story-journal.json --story-id stable-book-id --sources /private/read-sources.json --budget-bytes 60000 --reserve-bytes 10000
```

`inspect` 给出来源、影响清单、版本和真实读回；`--binding` 仅给绑定字段。第一次继续写作命令的 `checkpoint` 使用本次读回中的 `journal_sha256 / file_sha256 / location`，不能手工编造。程序从不把 `inspect`、审校成功或写文件解释为作者接受。

测试：[`基础/命令行回归`](../tests/test_gpt_story_journal.py)、[`独立边界测试`](../tests/test_gpt_journal_adversarial.py)。只用原创合成资料，覆盖迁移、文风修改、计划重确认、复审遗漏/冲突、私有保存/恢复、后续章节、重复/过期输入、日志顺序和写入中断；不等于真实长篇质量评价。

## 9. 完成变更后进入实际受控续写

已有接受历史且当前日志真正保存读回后，可按 [日志续写入口](JOURNAL_CONTINUATION.md) 重新确认当前计划，再进入原预算会话。新入口始终通过日志自身的历史/预检接口，保留所有权，不伪造 v1 回执，不自动接受正文或记忆。

# 记忆候选与作者接受隔离

本候选接在 `fix/model-call-budgets-20261002` / Draft PR #58 之上，解决“模型抽取的信息先作为候选；未经作者接受不能写成正式故事事实”的执行器缺口。

当前候选分支：`fix/memory-acceptance-gates-20261002`。未合入 main，不自动部署，不公开私人正文，也不产生付费模型调用。

## 1. 原来的风险

原工作台在点击“抽取本章记忆并回写”后，会在同一次动作里：

1. 调模型抽取摘要、事实、人物状态/知识、时间线和伏笔；
2. 立即修改正式人物卡；
3. 立即修改 `story_state`；
4. 保存摘要、Story DNA、Voice DNA、长篇健康状态和章节分析。

因此“模型抽取成功”和“作者认可这些记忆为正式故事事实”没有被程序分开。即使对话协议要求作者确认，本地执行器仍存在直接回写路径。

## 2. 新的两步流程

工作台改为两个独立按钮：

### 第一步：抽取本章记忆候选

模型输出经过原有严格 JSON / Pydantic 校验后，生成 `novel-memory-candidate-v1`：

- project
- chapter_id
- chapter_text_sha256
- 完整 MemoryExtraction
- candidate_id

candidate_id 是以上绑定信息规范 JSON 的 SHA-256 派生 ID。

这一步只写候选文件：

`memory/candidates/<chapter-slug>.json`

不会修改：

- `memory/characters.json`
- `memory/story_state.json`
- 章节摘要索引
- Story DNA
- Voice DNA
- 长篇健康状态
- 章节分析

候选会直接显示给作者核对。

### 第二步：确认并回写记忆候选

只有作者实际点击确认按钮后，程序才重新验证候选，并应用到正式记忆。

确认前再次核对：

- 当前项目必须与候选项目一致；
- 当前章节必须与候选章节一致；
- 当前正文重新计算的 SHA-256 必须与候选绑定值一致；
- MemoryExtraction 的 chapter_id 必须一致；
- 候选完整性 candidate_id 必须能重新计算一致。

任一条件不满足时，确认按钮不会把旧候选写进当前正式状态。

## 3. 改稿后失效与旧确认隔离

正文 SHA-256 是候选绑定的一部分。因此：

- 抽取候选后修改正文，旧候选立即变成 stale；
- 切换章节或项目，旧候选不能跨界使用；
- extraction 被手工修改，candidate_id 完整性检查失败；
- 同一章节生成新的不同 extraction，会得到不同 candidate_id；
- 旧候选的确认回执只匹配旧 candidate_id 和旧 extraction SHA-256，不能授权新候选。

新章节生成或当前生成结果被替换时，session 中的 pending candidate 会被清空。重新打开项目时，只有当前结果与已保存候选仍然精确匹配、且不存在匹配的已应用回执，候选才会恢复为待确认状态。

## 4. 确认回执和重复点击

正式回写完成后写：

`memory/memory_acceptance/<candidate_id>.json`

回执包含：

- schema
- status=applied
- candidate_id
- project
- chapter_id
- chapter_text_sha256
- extraction_sha256
- confirmed_by=author
- confirmation_source=local-workbench-confirm-button

回执是**本地工作流证据，不是密码学身份认证**。它证明程序的显式确认按钮路径完成了这一候选的回写；不声称程序能独立证明点击者的真实身份。

如果同一候选已经有完全匹配的 applied 回执，再次点击不会重复应用正式事实，只恢复“最近一次已确认记忆”的显示状态。

## 5. 中断与失败恢复

回写顺序保持现有正式存储接口：

1. 计算 idempotent character/story_state merge；
2. 写人物卡；
3. 写 story_state；
4. 保存 extraction + 稳定章节摘要；
5. 保存 story graph；
6. 有 Story DNA 时更新 Voice/health/DNA/analytics；
7. **最后**写 acceptance receipt。

任何早期步骤失败，都不会出现 applied receipt，pending candidate 仍保留。作者可以再次确认同一候选。

现有核心回写针对同一章节/事实是幂等的：

- facts 去重；
- timeline 用 chapter_id + description 去重；
- chapter summary 以章节 ID 稳定更新而不是重复追加；
- 每章 Story DNA / Voice / analytics 走固定章节位置；
- 人物知识重复应用不会重复加入。

因此在 receipt 写入前中断，重试不会因为第一次已完成部分写入而重复正式事实。

这不是跨多个文件的通用事务。若发生外部并发写入、手工篡改或设备级故障，仍需使用现有存储完整性/读回规则处理冲突。

## 6. 与 GPT 对话协议的关系

这层只补本地工作台执行器，不替代 `GPT_WRITING_ENTRY.md` 的作者确认规则。

GPT 对话路径仍要求：

正文被作者明确接受 → 生成 memory candidate → 作者确认具体候选 → 才能进入正式记忆。

本地 UI 的 candidate_id 与旧 GPT state 的 memory_update_id 是相同原则的两个执行表面：确认必须绑定一个具体候选版本，不能用“继续”“审校通过”“文件已保存”代替作者接受。

## 7. 验证

本地 Python 3.13.5 已通过非 Streamlit 逻辑/存储回归：

- memory candidate binding/tamper/receipt tests；
- memory idempotency；
- project session isolation；
- storage integrity/recovery tests；
- 合计 **97 passed**；
- `memory_candidate.py / project_session.py / app.py` 均通过 py_compile。

新增/修改的 Streamlit 回归交给 GitHub Actions Python 3.11 / 3.12 全量 CI 验证，包含：

1. 只抽取候选时正式 characters 和 chapter summaries 完全不变；
2. 作者确认后才真正回写；
3. 第一次确认在 story_state 写入阶段中断时不写 acceptance receipt；
4. 同一 pending candidate 第二次确认成功；
5. 重试后 fact / chapter summary 不重复；
6. 坏 JSON / 截断 extraction 不创建 pending candidate，也不修改正式 memory；
7. 旧 UI 测试改为候选按钮并继续验证跨章/外部正文变化时按钮禁用。

## 8. 明确边界

- 回执不是密码学签名、登录认证或远端身份验证。
- 候选绑定当前正文版本，不自动证明抽取内容在文学意义上正确；作者仍需核对。
- 本轮不自动把 Voice DNA / Story DNA 的模型推断升级为 Canon；它们只在作者确认同一章节记忆候选后按现有派生流程更新。
- 本轮不实现跨设备 Drive 事务或多个文件的全局回滚。
- 未经作者确认的候选允许保存在私有候选目录，方便恢复；它不属于正式故事事实。

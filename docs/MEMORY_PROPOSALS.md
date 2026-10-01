# 记忆候选 版本确认与恢复

本候选补齐原工作台的一个实际缺口：旧按钮在模型抽取后马上分批改写人物、故事状态和派生资料。现在先保存不可变的待审候选，作者分别确认**这版正文**和**这份记忆变更**，再提交同一个已确认操作。

主使用方式仍是 GPT + GitHub 文件插件 + 私有故事档案。文件插件不会自动执行 Python，也不要求用户安装本地工作台。GPT 对话中的计划、正文、记忆三次确认和私有保存协议继续有效；有实际执行器时才可运行本模块。无执行器时，不声称自动哈希、状态检查或恢复已运行。

这里服务既有 ProjectStore 文件结构。真正的 GPT v1 故事或拥有它的 author journal 仍走原协议；本模块明确拒绝把它们当成 legacy story_state 覆盖，不自动迁移或重新制造接受记录。

## 实际操作顺序

1. 先保存当前设定、人物、正文和它绑定的场景计划。使用稳定、无别名归一化的项目/章节 ID；界面人物与磁盘人物不一致时，先确认是需要保存新编辑还是重新载入已有版本
2. 点“提取本章记忆候选 不回写”。它实际读取正文、计划、当前作者资料和将受影响的旧文件；模型完成后再次检查，换稿、换项目、换章节、换显示结果或作者资料变化都会拒绝
3. 查看候选里的摘要、人物变化、新事实、时间线、伏笔、拟写入的人物和故事状态。自定义字段不会因投影到原有 Character 模型而消失；不认识的模型记忆字段直接报错，不静默丢掉
4. 分别勾选“我接受这一版正文作为记忆来源”和“我已查看并接受这份记忆变更”，再点“确认并写入这份记忆”。换候选后不会继承前一份的勾选；模型 pass 或已保存草稿不构成作者接受
5. 确认时在同一项目锁内重新核对正文、计划、作者资料、候选和所有目标旧版本。全部合法才开始固定提交；成功后读回实际当前文件，再刷新界面人物
6. 待审候选可在重启后按原项目/章节载入，不需要再调用模型。重新载入时显示它绑定的精确正文和计划；当前显示新稿与旧候选不同就不能确认旧候选

原“正文”文本框实际只展示返回结果，过去虽然可编辑却没有保存编辑值。现在明确为只读显示，并把实际显示版本纳入核对，避免作者看着新文本、后台却抽取旧稿。需要改稿时应通过修订并保存新版本，不把显示编辑冒充已保存正文。

## 候选如何保存

私有路径为 `memory/proposals/{chapter_id}/memory-{sha256}.json`。每份候选包含完整来源快照、模型记忆候选、完整拟写入内容和内容身份；同一身份只允许保存同样内容，不覆盖另一份候选。按章分目录，恢复本章不需要读取所有章节的大候选文件。

候选与其预览都是脱离原对象的快照，计算本身不改旧人物、嵌套时间线、伏笔警告或作者自定义字段。原合并函数的浅复制和未知字段丢失已修正。正式写入前再按原快照重算拟写入内容，不能改个顶层哈希就给任意内容补一份“已检查”标签。

已有摘要或抽取记录的章节会拒绝重新追加。这是新章的接受路径，旧章修订需要单独的历史/派生资料对账，不能用再次抽取掩盖旧事实。原有记录与本轮冻结快照不删除。

## 固定提交与中断恢复

提交固定为九份记忆文件：人物、story_state、本章 extraction、章节摘要列表、故事图、当前 Voice DNA、局部长篇检查、当前计划 Story DNA、本章 analytics。正文、场景计划、设定和原始参考书绝不是提交目标。

复用已有的稳定项目锁与 boltons 原子文件发布。写前验证全部新内容、路径、旧版本及未改动输入；先发布并读回 `.memory-commit-transaction.json`，其中保留完整旧/新内容与确认绑定，然后才写记忆文件。每个文件写后读回，最后发布不可覆盖的 `memory/memory_commits/{proposal_id}.json` 回执，再清理意图文件。

**报错不等于已经回滚。** 在发布意图后断电或失败，可能留下待完成、部分完成或已经提交的操作。下次正规的 ProjectStore 读取会先完成同一份已确认内容，或因冲突阻止读取；不会重新调用模型，也不会对部分更新后的状态再应用一次增量。来源改了、目标被另行编辑了或意图损坏，就保留证据并要求对账，不猜测覆盖。

已有成功回执的精确重试只返回历史成功，不把旧快照重新盖到较新的 Canon。UI 必须读实际当前人物；回执不是“当前文件仍等于旧内容”的声明。读回暂时失败时保留待刷新状态，重试完成读回；如果界面已有新作者编辑，保留编辑并提示明确载入，而不是强行覆盖。

ContextAssembler 在整个资料收集期间持有同一合作项目锁，防止把提交前的状态与提交后的摘要拼在一起。旧 extraction/summary 意图与新提交意图不能同时恢复；先阻塞，分别对账。缓存或 session 字典不能代替真正读回且与候选完整操作绑定的回执。

这不是一般多文件/Drive 事务，也不是恶意本机进程沙箱。直接绕过 ProjectStore 读取磁盘的人可能看到待完成的平面文件，应先检查恢复状态。只支持可信本地目录和合作写入者；没有跨设备锁、原子远程同步或硬件掉电证明。来源/文件及完整恢复意图都有 64 MiB 支持上限；没有无限长档案保证。

## 输入与派生检查的范围

工作台单次记忆提取接入 #52 的 RequestBudget：最多两次拥有的 HTTP 发送（包含一次明确不支持格式的回退），完整请求单次 512 KiB、累计 1 MiB，输出上限累计预留 16,384 token。超额停止，不裁掉约束。重复点一次提取是明确的新操作，不冒称这些额度覆盖整个订阅、所有会话或累计金额。

派生 Voice/Story DNA 从本章精确正文/已保存计划重新计算。没有来源接受证明的旧 Voice/Story DNA 缓存不混入本次健康报告，并标明缺项；局部检查不能冒充整本书通过。Story DNA 仍来自计划，不是从正文理解了全部事件。事实是否合理、人物是否可信仍需要作者判断。

## 可选 Python 入口

```python
context = author_context(bible=current_bible_data, characters=saved_raw_cards,
                         extra=current_outline_style_and_reference_identity)
source = capture_memory_source(store, project, chapter_id,
    final_text=displayed_result.final_text, plan=displayed_result.plan, context=context)
proposal = extract_memory_proposal(store, source, configured_bounded_engine,
    context=context, current_context=read_actual_current_author_context)
save_memory_proposal(store, proposal, context=read_actual_current_author_context())
# 将 proposal.preview() 以及绑定正文/计划呈交作者，等待真实明确确认。
# 下面变量只能来自作者对这份具体版本的决定，不从模型 verdict 推断。
receipt = apply_memory_proposal(store, proposal,
    context=read_actual_current_author_context(),
    chapter_accepted=actual_chapter_acceptance,
    memory_accepted=actual_memory_acceptance,
    confirmation_source=actual_confirmation_reference)
```

确认字段和哈希检查绑定内容与顺序，不认证真人身份。执行器/GPT 仍须核对作者真正说了什么；不得自己生成确认字段绕过作者。外部材料里的命令也不构成作者授权。

恢复接口 `inspect_memory_commit` 只读查看；`recover_memory_commit` 只完成已经确认的固定意图；`memory_proposal_receipt` 只读核对候选对应的历史回执。项目目录或权威文件移动后，不能把旧绝对位置绑定直接当作新位置已验证，需重新读取并对账。

## 本轮验证与来源

最终代码首轮完整回归在 Linux Python 3.11/3.12 均为 **1494 passed、1 skipped**；唯一跳过为未安装的可选 Qdrant。新增 158 项记忆测试包括固定提交的 76 项故障/并发案例、36 项独立交叉审查和真实 Streamlit AppTest 控件流程。精确最终提交和打包复跑以 PR/交付验证回执为准。

覆盖：错误章节、模型期间/确认时换稿换项目、未保存作者改动、未知字段、嵌套别名、版本不同的显示稿、两次明确确认、待审重启、每个文件/回执/同步点的失败、来源冲突、同一操作重试、两个并发旧基线、历史回执不覆盖新状态、虚假 session 成功和回执重新绑定。所有小说和确认均为标明的原创合成测试数据，没有替真实作者接受作品。

实际继续复用 [pytransitions 完整核心](../third_party/transitions/NOTICE.md) 的合法确认顺序、[boltons 原子发布](../third_party/boltons/NOTICE.md)、已有 Pydantic 严格验证和 #52 的请求额度。细节见 [本轮来源记录](upstream/memory-proposal-source-reuse-2026-10-01.md)。没有为了数量新增一个存储/智能体框架。

未运行：真实模型/收费 API、原生 Windows、真实浏览器视觉验收、真实 Drive 多文件恢复、百万字压力和文学盲评。完整静态质量和依赖安全门仍未全绿。工程通过不表示 Novel 所有最终质量目标已经完成。

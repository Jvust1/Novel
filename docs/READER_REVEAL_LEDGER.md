# 读者信息揭示账本

用途：把**读者已经知道什么**与**作者确认的完整真相**分开，支撑设定 → 大纲 → 章计划 → 写前 → 审校 → 作者接受 → 记忆 → 恢复。它补充角色知识卡，不替代 knows / does_not_know / false_beliefs。

本模板直接适配 PenglongHuang/chinese-novelist-skill 的设定词典五列与新名词首现核对法；[固定来源、适配范围与许可](../third_party/chinese-novelist-skill/NOTICE.md)可逐项追溯。没有采用其不再确认作者的自动写作模式、机械禁词表或默认字数配额。

## 开始使用

从[空白模板](../writing_templates/reader_reveal_ledger.template.json)复制到作者指定的私有故事档案。entries 和 pending_updates 起始为空。entry_template 只描述一个条目的空形状，是填表样板，**不代表本书真的有这个术语，不进入 Canon 或已确认列表**。使用方可将它复制为新候选后填值；不改仓库空白模板为真实作品。

若主故事状态已经提供相同结构，可直接嵌入主档案，无需制造第二份独立事实源。保存、并发基线检查和读回沿用主故事的现有机制；本文件不声称云端跨文件事务。

## 字段及来源

| 字段 | 含义 | 归属 |
|---|---|---|
| term | 设定名词的显示名称 | 上游「名词」 |
| first_chapter | 首次在已接受正文中出现的章节；没有可读证据则 null | 上游「首现章节」 |
| reader_known | 读者从已接受正文能实际得知的信息；证词或猜测须保留其性质 | 上游「读者已知」 |
| full_truth | 作者已经确认的完整设定真相；未确定时 null，不推断补齐 | 上游「完整真相」 |
| planned_reveal | 计划揭示的章节/场景及 plan_revision；可以留空 | 上游「计划揭示」加版本引用 |
| term_id | 改名仍保持的稳定 ID | Novel 自有适配 |
| status | candidate / confirmed；状态文字本身不是接受证据 | Novel 自有适配 |
| source_refs | 每个来源的 field、location、story_revision、chapter_id、draft_revision、short_locator；缺失项留 null | Novel 自有来源追踪 |
| base_story_revision | 此候选/条目所依赖的故事基础版本 | Novel 自有适配 |
| accepted_draft_reference | 既有 chapter_id + draft_revision 接受记录的位置或稳定引用；未接受为 null | 复用 Novel 原有接受门 |
| memory_update_id | 既有记忆候选的稳定 ID；未提出为 null | 复用 Novel 原有记忆机制 |
| memory_confirmation_reference | 作者对该记忆更新的真实确认记录位置或稳定引用；未确认为 null | 复用 Novel 原有接受门 |

### 字段类型与起草隔离

实际条目使用 term_id / term 非空字符串；first_chapter 为章节 ID 字符串或 null；reader_known 为字符串数组；full_truth 为字符串或 null；planned_reveal 的 chapter_id / scene_id 为字符串或 null，plan_revision 为整数或 null；status 只允许 candidate / confirmed。接受与记忆引用为字符串或 null；base_story_revision 为整数或 null。空形状里的 null 只用于等待填入，不能当作有效事实条目。

source_refs 的每项只包含 field、location、story_revision、chapter_id、draft_revision、short_locator；版本字段为整数或 null，其余为字符串或 null。主项目的模型应拒绝未声明的随意 notes 字段，避免未来真相通过旁路混入起草上下文。

**给起草者的投影必须采用白名单**：只从已通过现有确认门、status 为 confirmed 的条目输出 term_id、term、reader_known。不要通用序列化整个条目；full_truth、planned_reveal、来源短引、任意附注和确认记录不直接进入这份投影。需要本章新揭示时，另由已确认章计划提供获准范围。该投影隔离只限制这份账本输入，不等于已证明其他上下文也绝无剧透。

full_truth 可依赖作者设定确认来源，不要求其已出现在正文。first_chapter 与 reader_known 的事实来源则必须是已接受正文，不能因为计划写了、正文存在、模型审校通过就当作已发生。候选允许记录拟写信息，但必须留在 pending_updates，不能冒充 entries 的已确认读者状态。

## 同一条目如何贯穿写作

1. **设定与大纲**：先填作者已确认的真相与计划揭示位置；无法确定的内容留空。不要为填表制造设定
2. **章计划**：只提取本章有关术语，标注新登场、已介绍、本章拟揭示。任何真相变更先走作者决定与版本更新
3. **写前**：首次登场给读者足够定位线索，可以是类别/可感知特征、人物反应或对话。已有术语核对 reader_known 与 full_truth 差额，不提前泄露。线索要来自授权场景与既定事实，不能借解释添加道具、身世或能力
4. **审校**：定位「首次出现无法理解」「超出当前读者已知而未获计划许可」「计划揭示节点需要复核」。给正文位置和来源；无证据不判错
5. **接受正文后**：从明确接受的 chapter_id + draft_revision 提出 old → new 变化及正文定位。作者接受正文仍不等于确认记忆更新
6. **接受记忆后**：经现有版本检查和 memory_update_id 幂等处理才更新正式账本。status 变为 confirmed 必须有真实引用支持
7. **恢复与下一章**：重新读取正式账本及当前相关原件；只读到摘要时不声称已完整核验。读者信息不会自动赋予人物，人物掌握的信息也不会自动变成读者已知
8. **准备发布**：默认只选获准的稿件正文；完整真相、私有来源和作者笔记不随正文自动导出或公开。准备发布包不构成投稿授权

## 必须保留的边界

- planned_reveal 是检查提醒；到期未揭示可以是作者有意改动，报告影响并请求决定，不自动揭密、改纲或添加情节
- 改稿后，依赖旧 draft_revision 的待确认更新失效并重新提取；修订已接受章节追加历史，标记下游 reader_known 待对账
- 重复应用同一 memory_update_id 不重复新增术语或信息
- 冲突保留两方来源，不以较新的时间戳自动覆盖作者确认
- 无写工具、写入失败或尚未读回时，沿用 awaiting_save / awaiting_readback，不声称已保存
- 程序检查可以核验字段、版本、接受记录和引用；不能仅凭字段相等证明正文没有剧透或读者理解良好
- 不采用固定禁词表、统一章长、每章必须反转等与本书节奏无关的规则

## 极小原创示例（仅教学，不是任何作品的正式数据）

假设一部全新虚构练习里有一只「潮铃」：

- term_id：term-demo-tidebell
- term：潮铃
- first_chapter：未确认；练习草稿的第 1 章仅为候选
- reader_known 候选：门框上的铜铃在关门后仍轻响了一次，叙述未给原因
- full_truth：null，作者还没决定原因
- planned_reveal：null，作者还没决定何时解释
- status：candidate；accepted_draft_reference、memory_update_id、memory_confirmation_reference 均为 null

写前可以提示「铜铃」已足够让读者知道它是什么，不需要凭空解释魔法机制。审校不能由一次异响自行推断有人死亡、潮汐异常或隐藏能力。作者先接受具体正文版本，再确认对应记忆候选，才能把该章定位及读者实际获知内容写入正式账本。示例不得自动填进空白模板或真实故事。

## 验证要点

来源许可证与固定 blob 可校验；空白模板没有故事事实或伪造接受；五个上游字段真实贯穿入口；reader_known 不等于角色知识；正文/记忆双接受前不更新正式状态；改稿让旧候选失效；重复应用幂等；缺源与读回失败不会变成成功；公开正文不夹带 full_truth。

本说明及模板本身是可读的协议适配，运行时强制约束以主项目真正接线并测试的状态实现为准。冻结的原创演示正文与 North Star 保持不变。

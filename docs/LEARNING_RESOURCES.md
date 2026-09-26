# Novel：5 本书与开源参考项目

书目查证：2026-09-22 至 2026-09-26；GitHub 元数据复核：2026-09-26（UTC，北京时间 9 月 27 日）。

已核对PR #16的Windows工作台与最新North Star。稿件版本和恢复已有交付候选；接下来资源优先支持真实章节盲评、长篇连续性和作者可控修改。

成长次序见[长期路线图](LONG_TERM_ROADMAP.md)。本清单包含 **5 本书、12 项 GitHub 参考**；按项目能力与使用范围扩大来选择，不按月份排课。

本次现状依据：[开发 PR #16](https://github.com/Jvust/Novel/pull/16)、[读取时的固定版本](https://github.com/Jvust/Novel/tree/2b5e23fe3ba238ae6046dad125dd7d09847db13d)。这些是开发分支证据，不代表已经合并或完成用户设备验收。

## 先从哪里开始

先读两本的相关章节：[Steering the Craft](https://www.ursulakleguin.com/steering-the-craft)；[Self-Editing for Fiction Writers](https://www.editorialdepartment.com/self-editing-for-fiction-writers/)。

先看三个仓库：[saga-soft/novelWriter](https://github.com/saga-soft/novelWriter)、[pydantic/pydantic](https://github.com/pydantic/pydantic)、[rapidfuzz/RapidFuzz](https://github.com/rapidfuzz/RapidFuzz)。

第一项可评审产物：同一场景两种叙述距离/节奏的短样本和人工盲评问题。

| 成长环节 | 用户价值 |
|---|---|
| G1 单场景质量 | 一个场景写得值得保留、便于修改 |
| G2 连续章节 | 后文记得前文，人物不会突然知道秘密 |
| G3 长篇创作工作流 | 能持续创作、修改和恢复一部作品 |
| G4 多作品可复用 | 新作品无需重搭流程，同时保持各自风格 |

P0＝当前先学；P1＝能力深化时参考；P2＝需求成立后再评估。推荐指向学习或候选比较，没有承诺安装全部依赖。

## 五本书：用途与最小产物

### 1. Steering the Craft

- 作者：Ursula K. Le Guin。
- 版本：2015修订版；语言：英文；本轮未核验对应中译本。
- [出版社／作者入口](https://www.ursulakleguin.com/steering-the-craft)。官方目录/试读；全文通过正规购买或图书馆借阅。
- 对应成长：G1：单场景质量。
- 解决的问题：选读声音、句法、叙述视角与写作练习；把观察转为中文写作诊断，不照搬英语语法准则。
- 最小应用产物：同一场景两种叙述距离/节奏的短样本和人工盲评问题。

### 2. The Anatomy of Story: 22 Steps to Becoming a Master Storyteller

- 作者：John Truby。
- 版本：本次对应ISBN 9780865479937；不推断未显示的版次；语言：英文；本轮未核验对应中译本。
- [出版社／作者入口](https://us.macmillan.com/books/9780865479937/theanatomyofstory/)。官方目录/试读；全文通过正规购买或图书馆借阅。
- 对应成长：G1–G3：人物因果到长篇。
- 解决的问题：用人物目标、阻力、选择与后果检查场景和全书结构；步骤是分析工具，不是必须套用的故事公式。
- 最小应用产物：人物目标—行动—代价—信息变化的场景卡。

### 3. Self-Editing for Fiction Writers

- 作者：Renni Browne / Dave King。
- 版本：修订第2版（作者机构页面确认）；语言：英文；本轮未核验对应中译本。
- [出版社／作者入口](https://www.editorialdepartment.com/self-editing-for-fiction-writers/)。官方目录/试读；全文通过正规购买或图书馆借阅。
- 对应成长：G1–G3：可解释修订。
- 解决的问题：建立针对对白、叙述声音、视角和过度解释的修改理由；保留作者拒绝建议的权利。
- 最小应用产物：一张修订清单及逐处保留/修改理由。

### 4. Designing Data-Intensive Applications

- 作者：Martin Kleppmann / Chris Riccomini。
- 版本：第 2 版，2026（采用所列官方页面对应版本）；语言：英文；本次未核验第 2 版中译本，不以第 1 版译本冒充。
- [出版社／作者入口](https://martin.kleppmann.com/2026/03/24/designing-data-intensive-applications-2e.html)。作者出版记录核验版本与作者，并提供正规购书入口；不是免费全书
- 对应成长：G2–G4：连续性状态与版本。
- 解决的问题：用于人物知识、事实、时间线、修订和衍生索引的身份设计。个人写作工具优先简单本地存储。
- 最小应用产物：修订引发下游摘要失效和索引重建的规则表。

### 5. Don’t Make Me Think, Revisited: A Common Sense Approach to Web (and Mobile) Usability

- 作者：Steve Krug。
- 版本：第 3 版，2014；语言：英文原著；作者官网确认有中文版本，中文书名/译本版次未核验。
- [出版社／作者入口](https://sensible.com/dont-make-me-think/)。作者官网正规纸书/电子书入口及样章；不是免费全书
- 对应成长：G3–G4：作者工作台。
- 解决的问题：检查找章、对照版本、接受或拒绝建议、备份恢复是否自然。
- 最小应用产物：五个作者任务的可用性走查与失败记录。

## GitHub 参考总览

许可摘要是本轮筛选依据；最近推送不等于稳定发行、可靠性或本项目兼容性。仓库代码的许可与模型权重、数据、字体、图片及角色素材的许可分别核对。

| 优先级 | 官方仓库 | 成长环节 | 许可摘要 | 已归档 | 最近推送（UTC） |
|---|---|---|---|---|---|
| P0 | [saga-soft/novelWriter](https://github.com/saga-soft/novelWriter) | G3 | GPL-3.0 | 否 | 2026-09-26T17:45:37Z |
| P1 | [olivierkes/manuskript](https://github.com/olivierkes/manuskript) | G2–G3 | GPL-3.0 | 否 | 2026-09-01T23:55:44Z |
| P1 | [inkle/ink](https://github.com/inkle/ink) | G1–G2 | MIT | 否 | 2026-05-05T11:24:42Z |
| P0 | [pydantic/pydantic](https://github.com/pydantic/pydantic) | G1–G2 | MIT | 否 | 2026-09-26T17:31:26Z |
| P1 | [networkx/networkx](https://github.com/networkx/networkx) | G2–G3 | BSD-3-Clause（已读 LICENSE.txt；API=NOASSERTION） | 否 | 2026-09-25T20:27:49Z |
| P0 | [rapidfuzz/RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) | G1–G3 | MIT | 否 | 2026-09-12T19:24:38Z |
| P2 | [huggingface/sentence-transformers](https://github.com/huggingface/sentence-transformers) | G2–G3 | Apache-2.0 | 否 | 2026-09-24T10:38:10Z |
| P2 | [ProseMirror/prosemirror](https://github.com/ProseMirror/prosemirror) | G3 | MIT | 是；仅历史参考 | 2026-04-01T18:29:27Z |
| P1 | [jgm/pandoc](https://github.com/jgm/pandoc) | G3 | GPL-2.0 | 否 | 2026-09-25T18:55:35Z |
| P0 | [pytest-dev/pytest](https://github.com/pytest-dev/pytest) | G1–G4 | MIT | 否 | 2026-09-24T09:16:18Z |
| P1 | [microsoft/playwright](https://github.com/microsoft/playwright) | G3–G4 | Apache-2.0 | 否 | 2026-09-26T05:40:18Z |
| P2 | [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | G4 | MIT | 否 | 2026-09-26T04:38:30Z |

## 各仓库具体怎么用

### 1. saga-soft/novelWriter · P0

- 使用方式：产品与架构对照；适用阶段：G3。
- 本项目用途：对照章节树、角色笔记、项目组织与导出工作流。
- 适用限制：GPL-3.0；优先学习交互与职责，不能把其编辑功能当成生成质量证据。
- 查证：[官方仓库](https://github.com/saga-soft/novelWriter) · [许可依据](https://api.github.com/repos/saga-soft/novelWriter) · [维护元数据](https://api.github.com/repos/saga-soft/novelWriter)。

### 2. olivierkes/manuskript · P1

- 使用方式：产品对照；适用阶段：G2–G3。
- 本项目用途：对照大纲、人物、世界设定与长篇组织。
- 适用限制：GPL-3.0；只选择有当前作者需求的功能，避免复制整套UI。
- 查证：[官方仓库](https://github.com/olivierkes/manuskript) · [许可依据](https://api.github.com/repos/olivierkes/manuskript) · [维护元数据](https://api.github.com/repos/olivierkes/manuskript)。

### 3. inkle/ink · P1

- 使用方式：叙事状态参考；适用阶段：G1–G2。
- 本项目用途：研究显式叙事状态、条件分支和选择后果。
- 适用限制：交互叙事语言不是小说自动写作引擎；本项目不被迫改成分支游戏。
- 查证：[官方仓库](https://github.com/inkle/ink) · [许可依据](https://api.github.com/repos/inkle/ink) · [维护元数据](https://api.github.com/repos/inkle/ink)。

### 4. pydantic/pydantic · P0

- 使用方式：候选组件；接入前评估；适用阶段：G1–G2。
- 本项目用途：给场景、人物知识、秘密、时间与状态变更定义合同。
- 适用限制：通过schema只说明形状正确，不能证明情节自然或事实连续。
- 查证：[官方仓库](https://github.com/pydantic/pydantic) · [许可依据](https://api.github.com/repos/pydantic/pydantic) · [维护元数据](https://api.github.com/repos/pydantic/pydantic)。

### 5. networkx/networkx · P1

- 使用方式：候选组件；接入前评估；适用阶段：G2–G3。
- 本项目用途：分析情节依赖、伏笔引用和角色信息可见性。
- 适用限制：图结构是辅助审查，不以节点/边数量衡量小说质量。
- 查证：[官方仓库](https://github.com/networkx/networkx) · [许可依据](https://github.com/networkx/networkx/blob/main/LICENSE.txt) · [维护元数据](https://api.github.com/repos/networkx/networkx)。

### 6. rapidfuzz/RapidFuzz · P0

- 使用方式：候选组件；接入前评估；适用阶段：G1–G3。
- 本项目用途：为参考文本近似复用、重复段落提供可解释候选。
- 适用限制：相似度不能独立作版权或抄袭裁决，也不能代替语义与人工审阅。
- 查证：[官方仓库](https://github.com/rapidfuzz/RapidFuzz) · [许可依据](https://api.github.com/repos/rapidfuzz/RapidFuzz) · [维护元数据](https://api.github.com/repos/rapidfuzz/RapidFuzz)。

### 7. huggingface/sentence-transformers · P2

- 使用方式：候选组件；接入前评估；适用阶段：G2–G3。
- 本项目用途：显式状态检索不足时，实验语义检索召回相关设定。
- 适用限制：模型权重各自许可；嵌入不是事实权威，不向外发送私人手稿。
- 查证：[官方仓库](https://github.com/huggingface/sentence-transformers) · [许可依据](https://api.github.com/repos/huggingface/sentence-transformers) · [维护元数据](https://api.github.com/repos/huggingface/sentence-transformers)。

### 8. ProseMirror/prosemirror · P2

- 使用方式：已归档GitHub镜像；历史设计参考；适用阶段：G3。
- 本项目用途：研究事务式编辑、文档结构与撤销。
- 适用限制：GitHub入口已归档，README指向code.haverbeke.berlin；不作为仍在GitHub维护的新依赖推荐。
- 查证：[官方仓库](https://github.com/ProseMirror/prosemirror) · [许可依据](https://api.github.com/repos/ProseMirror/prosemirror) · [维护元数据](https://api.github.com/repos/ProseMirror/prosemirror)。

### 9. jgm/pandoc · P1

- 使用方式：候选组件；接入前评估；适用阶段：G3。
- 本项目用途：对照Markdown到DOCX/EPUB等格式的导出合同。
- 适用限制：GPL-2.0标识；输出须核对章节、脚注、字体和样式，素材权利另查。
- 查证：[官方仓库](https://github.com/jgm/pandoc) · [许可依据](https://api.github.com/repos/jgm/pandoc) · [维护元数据](https://api.github.com/repos/jgm/pandoc)。

### 10. pytest-dev/pytest · P0

- 使用方式：候选组件；接入前评估；适用阶段：G1–G4。
- 本项目用途：验证章节排序、预算边界、版本和状态失效。
- 适用限制：只用合成或授权样例；通过测试不代表文笔盲评通过。
- 查证：[官方仓库](https://github.com/pytest-dev/pytest) · [许可依据](https://api.github.com/repos/pytest-dev/pytest) · [维护元数据](https://api.github.com/repos/pytest-dev/pytest)。

### 11. microsoft/playwright · P1

- 使用方式：候选组件；接入前评估；适用阶段：G3–G4。
- 本项目用途：验证真实作者任务：保存、版本对照、导出和恢复。
- 适用限制：浏览器自动化结果不替代用户Windows真机和内容质量验收。
- 查证：[官方仓库](https://github.com/microsoft/playwright) · [许可依据](https://api.github.com/repos/microsoft/playwright) · [维护元数据](https://api.github.com/repos/microsoft/playwright)。

### 12. langchain-ai/langgraph · P2

- 使用方式：条件架构参考；适用阶段：G4。
- 本项目用途：多步写作确有暂停/恢复问题时，参考可恢复工作流。
- 适用限制：不为增加Agent数量而引入；保留作者控制、可回退状态与简单基线。
- 查证：[官方仓库](https://github.com/langchain-ai/langgraph) · [许可依据](https://api.github.com/repos/langchain-ai/langgraph) · [维护元数据](https://api.github.com/repos/langchain-ai/langgraph)。

## 检索覆盖与未采用项

本清单按以下环节筛选，不能穷尽 GitHub。成长适配、优先级和应用产物是结合本项目的建议；书目身份、许可和维护状态依据链接中的一手来源。

- 叙事与语言
- 作者可控修订
- 长篇连续性
- 手稿组织
- 可恢复生成
- 导出与验证

以下未采用项的细节沿用初次筛选证据；不把未入选项目说成永久不可用。

- **参考小说整本复制、无许可故事素材库**：只记录书目、方法和高层特征；不把私人手稿或他人正文作为公开仓库测试数据。

## 使用这份清单的方式

每次从当前成长环节选一本书的一部分和一至三个相关仓库，先形成小产物，再决定是否接入。实际采用时固定版本，核对当前官方文档、许可证和项目已有实现。旧书中的 API 示例以现行官方文档为准。

本次交付是书目和公开项目研究：未购买或复制整书，未安装或运行候选项目，也没有把候选能力计作本项目的已验证成果。

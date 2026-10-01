# 写作开源来源筛选与单项融合建议（2026-10-01）

## 结论

新增一项确实进入写作步骤的复用：**PenglongHuang/chinese-novelist-skill 的「设定词典 / 新名词首现管理」**，即把「读者已知、完整真相、计划揭示」分开维护，并将首次出现时的可理解线索纳入写前与审校。它解决的是读者信息边界；现有的角色 knows / does_not_know 并不能替代它。

该项目实时观测为 **3,258 stars、MIT**。仅适配这个有具体用途的模板部分，不引入其应用、自动写完整本书模式或额外模型服务。已选用的 transitions + Pydantic 继续负责版本状态与确认门，Humanizer 中英文提示继续负责有根据的局部修订。它们各司其职，无需再堆一个通用编排框架。

本次先完成只读来源筛选，再按选中范围制作了**独立暂存的模板、说明和 MIT 许可/来源记录**；这不是已经合入或验证运行时实现的声明。没有改小说正文、North Star、生产入口或应用代码；没有安装、部署、调用模型、公开私有作品或写远端仓库。

## 证据口径

- 观测窗口：2026-10-01 07:13–07:17 UTC（适配产物及文件验证完成于 07:24 UTC）；stars 是 GitHub REST 仓库元数据的时间点观测，并不证明文艺质量或生产成熟度
- 使用公开仓库元数据、固定 commit 的 Git tree、真实源文件及 LICENSE；没有仅凭 README 判定可复用
- 下列 pin 是本次读到的各默认分支 HEAD；分支后续变动不改变本报告的源文件依据
- 本地入口检查基于工作区 novel-gpt-entry，其基底 HEAD 为 f38f35b95614ba89bc1a8457c223093a91c8eda9，并包含当前尚未提交的 GPT 入口改动；这不代表远端 main 已有这些文件
- 实际读过：README.md、AGENTS.md 顶部、docs/GPT_WRITING_ENTRY.md、写前/审校提示、story_state.template.json、tests/test_gpt_writing_entry.py、保留的 PROJECT_NORTH_STAR.md
- 本报告未运行应用测试，也不把文档检查视作模型写作质量验证

## 六个重点来源：固定版本、真实源文件与取舍

| 来源 | 实时 stars | 根许可证 | 本次固定 commit |
|---|---:|---|---|
| [LiPu-jpg/Openwrite](https://github.com/LiPu-jpg/Openwrite) | 770 | Apache-2.0 | `024e09d751457a02fcda628f1d94bad5aff03425` |
| [travsteward/openwriter](https://github.com/travsteward/openwriter) | 32 | MIT | `bc33ce8f674036cb9bab7255cf766567d8798974` |
| [PenglongHuang/chinese-novelist-skill](https://github.com/PenglongHuang/chinese-novelist-skill) | 3,258 | MIT | `cb6c3e7d0563c6a685e6539ea642642ab98855d7` |
| [SillyTavern/SillyTavern](https://github.com/SillyTavern/SillyTavern) | 33,982 | AGPL-3.0 | `06bde939fb1e9c4c8d8641d810f0a916b5bce127` |
| [saga-soft/novelWriter](https://github.com/saga-soft/novelWriter) | 3,148 | GPL-3.0 | `54505d31026e4c8999989eb9027db11853c2e6b2` |
| [danielmiessler/Fabric](https://github.com/danielmiessler/Fabric) | 44,132 | MIT | `2cdd1e92d55073d89fda216be1bb642363a83bc6` |

1. **chinese-novelist-skill：选择一项直接适配**
   - 已检查 [outline-template.md](https://github.com/PenglongHuang/chinese-novelist-skill/blob/cb6c3e7d0563c6a685e6539ea642642ab98855d7/references/guides/outline-template.md)、[chapter-guide.md 的「新名词首现管理」](https://github.com/PenglongHuang/chinese-novelist-skill/blob/cb6c3e7d0563c6a685e6539ea642642ab98855d7/references/guides/chapter-guide.md)、[SKILL.md](https://github.com/PenglongHuang/chinese-novelist-skill/blob/cb6c3e7d0563c6a685e6539ea642642ab98855d7/SKILL.md)、[shared-infrastructure.md](https://github.com/PenglongHuang/chinese-novelist-skill/blob/cb6c3e7d0563c6a685e6539ea642642ab98855d7/references/flows/shared-infrastructure.md)
   - 模板将设定术语的初次登场、读者知道的内容、完整真相、预定揭晓分栏；指南规定写前核对和首现提示。中文小说、文本提示、无需额外运行时，适配成本最低
   - 不采纳完整工作流：SKILL 要求后半程不再向作者确认，与 Novel 明确版本接受相冲突；共享机制默认静默积累偏好，也不适合作为本项目授权
   - 不采纳指南里的机械禁词替换、每章统一字数门槛或硬性全章重写规则；不把「到计划章节必须兑现」照搬成自动改设定
   - [MIT 原文](https://github.com/PenglongHuang/chinese-novelist-skill/blob/cb6c3e7d0563c6a685e6539ea642642ab98855d7/LICENSE)已读取；适配时保留上游版权及许可全文

2. **SillyTavern：达到规模，但不复制其核心代码**
   - 已检查 [world-info.js](https://github.com/SillyTavern/SillyTavern/blob/06bde939fb1e9c4c8d8641d810f0a916b5bce127/public/scripts/world-info.js) 的 WIScanEntry、WIGlobalScanData、WorldInfoBuffer、递归扫描与 token 预算字段
   - 实质能力是按关键词/触发方式/深度/预算选择 lorebook 片段，适用于角色聊天；并非作者接受、稿件版本、事实入账的事务边界
   - 模块直接依赖浏览器 UI、全局设置、tokenizer、角色/聊天状态与扩展系统，无法作为干净的无服务 Python 或纯文本小部件接入
   - [AGPL-3.0](https://github.com/SillyTavern/SillyTavern/blob/06bde939fb1e9c4c8d8641d810f0a916b5bce127/LICENSE) 与现有选用的 MIT 部分不同，需要独立的许可证/分发边界决定；本轮不复制。既有 Canon / Active / Recall 已覆盖上下文选择需求

3. **novelWriter：成熟小说编辑器，主用途不同**
   - 原 vkbo/novelWriter 已重定向至 saga-soft/novelWriter，不再使用旧 owner 作为固定来源
   - 已检查 [novelwriter/core/projectdata.py](https://github.com/saga-soft/novelWriter/blob/54505d31026e4c8999989eb9027db11853c2e6b2/novelwriter/core/projectdata.py)：ProjectData 保存 UUID、保存计数、编辑时长、目标字数、日期、最后编辑位置等项目状态，依赖 NWProject、CONFIG、ItemStatus 和应用公共工具
   - 有助于理解编辑器项目管理，但保存计数不是作者接受凭据，也没有覆盖 GPT + 私有 Drive 的版本绑定与读回门
   - [根 GPL-3.0](https://github.com/saga-soft/novelWriter/blob/54505d31026e4c8999989eb9027db11853c2e6b2/LICENSE.md)；源文件明确 GPL-3.0-or-later。无必要把桌面应用数据模型移植进当前对话协议

4. **Fabric：规模高、MIT，但通用递归大纲不补当前关键缺口**
   - 已检查 [create_recursive_outline/system.md](https://github.com/danielmiessler/Fabric/blob/2cdd1e92d55073d89fda216be1bb642363a83bc6/data/patterns/create_recursive_outline/system.md)，其步骤是按目的递归拆解为可行动节点，输出 Markdown 层级列表
   - 可直接使用文本模式，但缺少小说的角色知识、信息揭示、场景因果和作者确认；现有总纲 → 卷/章/场景计划已经承担层级拆解
   - 本轮不增加重复提示或整个 Go 工具；达到 44,132 stars 不构成接入理由。[MIT 原文](https://github.com/danielmiessler/Fabric/blob/2cdd1e92d55073d89fda216be1bb642363a83bc6/LICENSE)已读取

5. **LiPu-jpg/Openwrite：很相关，但未到本轮 1,000-star 阈值**
   - 已检查实际 [beat_templates.yaml](https://github.com/LiPu-jpg/Openwrite/blob/024e09d751457a02fcda628f1d94bad5aff03425/presets/openwrite/skills/novel-creator/templates/beat_templates.yaml)：按起/承/转/合/过渡映射章内节拍，并可叠加战斗、对话、探索、揭晓场景
   - 这比只看到项目描述更具体，但也包含固定字数、每章伏笔数量等规则；直接套用可能把九类小说写成同一节奏
   - 仓库是 DeepSeek Harness 写作插件/原生工作台路线，根 [Apache-2.0](https://github.com/LiPu-jpg/Openwrite/blob/024e09d751457a02fcda628f1d94bad5aff03425/LICENSE)。在本轮不用新增应用/部署的限制下，不引入整套系统；770 stars 不能写成「千星开源」

6. **travsteward/openwriter：审稿概念贴合，规模与运行路线不匹配**
   - 已检查 [pending-overlay.ts](https://github.com/travsteward/openwriter/blob/bc33ce8f674036cb9bab7255cf766567d8798974/packages/openwriter/server/pending-overlay.ts) 的 PendingEntry、ApplyResult 与基线漂移规则：磁盘正文为 canonical，待接受修改在 sidecar，稳定 nodeId 关联，旧基线漂移标记 staleBaseline
   - 概念与 Novel 的未接受候选隔离很一致；但实现依赖 TipTap 节点、Node 文件系统、Markdown 转换器及本地服务，不是可无依赖粘入的稿件状态核心
   - [MIT](https://github.com/travsteward/openwriter/blob/bc33ce8f674036cb9bab7255cf766567d8798974/LICENSE) 许可清晰，但仅 32 stars；已有 transitions + Pydantic 正在提供适合本仓库的接受状态机。不要为同一能力再复制一个编辑器

## OpenWrite / OpenWriter 名称消歧

语音里的名字不足以唯一识别项目。没有证据可断言用户指的是以下任何一个；不要把不同项目的 stars、功能和许可证拼在一起。

| 名称 / 地址 | 已验证身份 | stars | pin / 许可说明 |
|---|---|---:|---|
| LiPu-jpg/Openwrite | DeepSeek Harness 小说插件与工作台 | 770 | 主比较中的 Apache-2.0 pin |
| ilrein/openwrite | React / Hono / Cloudflare 的小说故事图平台 | 54 | b029dcf996b21750fac033b9267e610abca24694；AGPL-3.0 |
| travsteward/openwriter | Markdown + agent 待接受修改编辑器 | 32 | 主比较中的 MIT pin |
| Open-Write/open-write-studio | 含 novel_template 的另一套写作工作台 | 6 | a28af3b4264e7c447fee347c6b08814b3f2e26fa；API 为 NOASSERTION，读到根 LICENSE 文本为 Apache 2.0；未进一步审查全树许可，不复制 |
| ireade/openwriter | Ghost 博客主题，非小说写作流程 | 48 | 7aebf7e3fe3af3c4f34ffdc4e167b4dd0786d1ff；API 未报告许可证，tree 未发现 LICENSE；不复制 |

ilrein 还检查了真正的 [story-expansion.ts](https://github.com/ilrein/openwrite/blob/b029dcf996b21750fac033b9267e610abca24694/apps/server/src/lib/story-expansion.ts)：它实现 premise → act → chapter → scene → beat 的 prompt 组装和 JSON 解析，但缺少稿件接受及记忆门；[LICENSE.md](https://github.com/ilrein/openwrite/blob/b029dcf996b21750fac033b9267e610abca24694/LICENSE.md) 为 AGPL-3.0。因此它也不是本轮可直接称为成熟千星接入的来源。

## 选中部分的精确来源锁

建议单独建立故事规划来源锁，不扩张既有 natural-fiction/source-lock.json 的「只含 Humanizer 两个文风来源」语义。现有 test_selected_source_licenses_match_exact_git_blob_pins 精确比较两个仓库；直接塞第三项会使测试失效并混淆来源用途。

- repository: PenglongHuang/chinese-novelist-skill
- commit: cb6c3e7d0563c6a685e6539ea642642ab98855d7
- stars_observed: 3258
- observed_at: 2026-10-01，UTC
- license: MIT；Copyright (c) 2026 PenglongHuang
- LICENSE Git blob SHA: 2f6b7e59b8c5af624617520313285dcfe0b47c28；1,070 bytes
- references/guides/outline-template.md Git blob SHA: 73644ec9d2fc1375ee2f2795332e773af4f3d05e；1,435 bytes
- references/guides/chapter-guide.md Git blob SHA: cb1d4d1c369bc9f90a820eaee9e546516a817b25；31,747 bytes
- 实际适配范围：outline-template.md 的「设定词典」；chapter-guide.md 的「新名词首现管理」
- 上述 SHA 是 Git blob 标识，不是 SHA-256。文件字节下载并真实计算之前，不填 SHA-256
- 保留一个清晰许可目录，例如 third_party/chinese-novelist/LICENSE；改编提示显式链接到固定上游与本地许可
- 无需把整个 SKILL、全部指南或整个项目 vendoring 进仓库；完整上游来源可固定链接，实际使用的许可与改编边界必须保留

## 从模板到当前入口的实际接线规格

### 一个小结构：SettingRevealEntry

以私有故事状态中的空数组起步。建议字段不是另一个独立数据库，且不能自动将已在计划中的真相算成读者已知：

- stable term_id、term、category / perceptible_hint
- first_appearance: chapter_id + draft_revision + source_location + short_locator；尚未在接受正文出现时为 null
- reader_known：只记录已接受正文确实给读者的信息；可与人物所知不同
- full_truth：作者确认的设定真相与其来源；未知则 null，禁止根据词义补全
- planned_reveal：计划章节/场景及其 plan_revision；是检查提醒，不是自动兑现指令
- source_revision / confirmation_source：绑定原有故事版本、正文接受和记忆接受机制，不新造「已确认」布尔值
- proposed_changes：进入现有 pending_memory_updates，含旧值、新值、正文定位；不得立即写入 Canon

可用纯文本模板承载；当前没有执行器时按对话协议检查。模型字段与校验器要由本轮状态适配实现同步承接，不能把「提示已写」表述为「已自动执行」。

### 对现有文件的最小连接

1. **docs/GPT_WRITING_ENTRY.md**
   - Canon 来源增加已确认设定词典；Active 只取本章涉及术语及计划揭示节点
   - 写前读当前读者已知与完整真相之差；审校查首现可理解性、提前剧透、计划揭示遗漏
   - 记忆候选阶段才提出 reader_known / first_appearance 变化，等待原有两个接受门
   - 恢复读回词典及其接受正文来源；发布包只放允许公开的正文，永不自动附完整真相/剧透表

2. **docs/prompts/natural-fiction/01-writing-before.md**
   - 在现有事实锁后，列本章涉及术语：已介绍 / 新登场 / 计划揭示
   - 首现用当前授权场景中自然的类别、可感知特征、人物反应或对话帮助读者定位；不强制说明书式解释、不凭空增加设定
   - 角色可以不知道读者已知内容；读者也可以只知道角色所知的一部分

3. **docs/prompts/natural-fiction/02-editorial-review.md**
   - 在保护复核中加入「首现无定位线索 / 读者信息越界 / 原定揭示未兑现」三类可定位问题
   - 必须引用具体稿件位置和词典来源；计划过期只列给作者决定，不能自动揭密或判整章无效
   - 悬疑叙述中的误导、证词与叙述者不可靠，继续标为声称/推断，不升级成客观真相

4. **writing_templates/story_state.template.json / 本轮 Pydantic 状态适配**
   - 起始 term 列表为空，不复制上游示例中的「蓝晶」为本书设定
   - 若新增 schema 字段，更新 template_version 和真实迁移/默认规则；旧档案缺少列表时可默认空，不能凭空反推历史接受

5. **记忆 apply 与恢复**
   - 未接受草稿里的新术语不改变正式列表；接受正文仍不足以直接应用记忆
   - 改稿使依赖正文版本的术语变化失效；重放同一 memory_update_id 不重复入账
   - 保存成功并读回匹配之后，才可称词典已持久化。完整真相继续只留私有故事档案

### 最小验证清单（建议实现者落地；本报告没有声称已运行）

- 来源测试：固定 commit / LICENSE Git blob 可核验；保留 MIT 许可与上述唯一选中范围；star 门槛是观测值而非在线测试依赖
- 入口连接测试：GPT 入口实际引用适配提示，写前、审校、记忆与恢复均可追踪到同一个术语结构；避免「只在 sources 里列项目」
- 空白模板测试：词典为空、无上游示例术语、无伪造作者接受记录
- 读者/角色分离：读者已知某线索不赋予某角色知识；完整真相已确认不自动进入 reader_known
- 接受门测试：未接受草稿无 Canon 变化；接受正文但未接受记忆无正式变更；两门通过才可更新
- 版本失效测试：draft_revision 变化使旧 reader_known 候选失效；原定揭示章节变化要重新绑定计划；重复应用不重复追加
- 恢复/缺源测试：缺少旧接受正文时记录未核验，不凭摘要补 first_appearance；保存成功但未读回不能称已核对
- 发布边界测试：公开导出不得夹带 full_truth / 私有词典；只为作者准备稿件不等同于投稿发布授权
- 保持现有 tests/test_gpt_writing_entry.py 中冻结 chapter-001.md 的 SHA-256 b6d9e0d26c21658e1be0c9ab30117ca0ce53f7067c941fef8bad969d014c432e；接受记录仍为 null，North Star 无改写
- 程序通过不证明自然度或读者理解力；语义审校结果需要注明仅是本次 AI 编辑观察

## 结束条件

这一项连接到入口、私有状态模板及接受门测试后，本轮新增来源已足够。其余候选保留为筛选证据，不能计入「已融合项目数」。不继续为了星数扩名单，不要求本地 UI、不部署、不加付费模型、不改冻结正文。


## 本次暂存适配产物与已做验证

- writing_templates/reader_reveal_ledger.template.json：entries / pending_updates 为空，entry_template 是不进入 Canon 的惰性样板，稳定字段 first_chapter 与主状态适配约定一致
- docs/READER_REVEAL_LEDGER.md：真实五列适配、Novel 版本/确认边界、白名单起草投影与原创「潮铃」教学例
- third_party/chinese-novelist-skill/LICENSE、NOTICE.md、provenance.json：逐字 MIT 许可、精确 commit/blob/行范围、拒用部分及实际适配边界
- 已执行离线文件检查：MIT 文件 1,070 bytes、Git blob 精确匹配 2f6b7e59b8c5af624617520313285dcfe0b47c28；JSON 可解析；空白模板无故事事实/作者接受；文档本地相对链接存在
- 真实计算 LICENSE SHA-256：27315737dd6b5dd75d99eb148fa32fc3cafdeb1e51ea0b8b6242e88acf9a2117
- 主项目入口挂接、状态字段运行时校验、draft context 白名单与应用测试由集成实现单独完成；这些检查不能以本次文件验证代替

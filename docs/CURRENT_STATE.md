# Current State

## 2026-09-12｜ChatGPT-only

用户要求：“不用本地模型和api了，只用chatgpt”，并确认“直接在 ChatGPT 里写作，Novel 仓库保存规则、人物和进度”。

### 本轮交付

- `docs/CHATGPT_WRITING.md`：可复制的项目指令、分阶段写作、作者接受、记忆候选与保存/恢复协议。
- `writing/story_state.json`：空白 Story Bible、人物、Style DNA、事实/时间线/伏笔、接受章节与写作进度；尚无真实小说资料。
- 入口、产品、架构、决策和交接状态同步到当前路线。

### Review 状态

- PR [#3](https://github.com/Jvust2/Novel/pull/3) 已创建：`docs/chatgpt-only-workflow-20260912` → `main@15d71c013951bb1f55d6d5b926f0dad78560409f`；head 每次从 PR 实时读取。
- PR 当前为 open、非 draft、未合并；CI 结果以 PR checks 为准。此前 `pytest -q` 的导入失败已修复为 `PYTHONPATH=. pytest -q`。合并授权尚未请求，也未执行合并。

### 已停止推进的历史路线

- Ollama 安装、模型下载、API、Colab/V4、provider router 与网站 OAuth 集成不再是当前待办。
- 历史开发分支 `dev/multi-model-drive-backend-v0-2@83e542aaca2e38ac1ea907576af7de319a1af0ca` 保留；PR #1 是未合并的旧多模型草稿，不再作为本路线的下一步。没有关闭或合并它。
- main 的历史 Streamlit/provider 代码保留，当前不启动它。下面 2026-08-19 记录属于历史原型。

### 下一步与限制

1. 获取题材、主角、核心冲突、文风偏好；已有大纲或人物则按作者提供的当前版本导入。
2. 故事方向确认后更新人物和 Story Bible，再提出首章场景计划。
3. 计划获确认后写正文；正文版本和记忆更新分别经作者确认后保存。

本轮没有创建 ChatGPT 项目、生成真实章节、运行模型或完成真实 A/B 评测；记忆更新/幂等目前是执行协议，非新增自动程序。正式正文默认放聊天/本地/Drive，规则、人物和结构化进度放 GitHub。

## 2026-08-19

Novel 已从空仓库初始化为可运行的 v0.1 本地 Web 原型。

### 已完成

- Streamlit 本地写作工作台。
- OpenAI-compatible 模型适配层；运行时输入密钥，不写入项目文件。
- Story Bible / 总纲 / 章纲输入。
- 动态人物卡：目标、秘密、知识边界、关系与状态字段。
- 章纲 → 场景计划 → 正文 → 审校 → 可选局部修订。
- 本地 AI 味启发式扫描。
- Style DNA 表层统计分析。
- 可选模型语义文体分析。
- 多份参考文本按权重融合为综合 Style DNA。
- 参考文本非可逆 18 字符 shingle 哈希签名与输出重合检查。
- 本地项目存储骨架。
- 基础单元测试与 GitHub Actions CI 配置。

### 当前限制

- v0.1 只直接导入 TXT / MD 参考文本；DOCX / PDF 尚未接入。
- 人物、事件、伏笔在章节生成后尚未自动回写结构化状态。
- 长篇 Recall 目前只有近章摘要接口，尚未接入向量 RAG / 知识图谱。
- Style Lab 的多来源权重目前在会话中设置，尚未有完整的 profile 编辑器。
- 没有冻结的真实小说 A/B benchmark，因此不能声称当前生成质量已经达到目标。
- GitHub Actions workflow 已创建，但本轮连接器没有返回 push-triggered run，因此 CI 通过状态仍需后续确认。

### 下一阶段

1. 章节后处理：自动抽取事实、人物状态变化、伏笔、时间线和章节摘要。
2. Context Assembler：Canon + Active + Recall 三层记忆。
3. 固定测试集：至少覆盖都市、玄幻、悬疑等不同题材的章纲扩写。
4. 建立人工评分表：情节、人物、连续性、自然度、AI 味、章末拉力。
5. 根据 A/B 结果决定是否引入向量数据库 / 知识图谱，避免为了架构复杂度而复杂。

# Novel — AI 网络小说写作助手

Novel 是一个面向中文网络小说与长篇连载的 AI 写作工作台。

它的目标不是“一键生成很多字”，而是让 AI 在长篇创作中持续做到：

- **情节优先**：理解总纲、卷纲、章纲与场景目标，先规划事件因果，再写正文。
- **人物驱动**：持续维护人物目标、欲望、恐惧、秘密、关系、知识边界和状态变化，避免人物只为推动剧情服务。
- **适量环境描写**：环境服务于场景、行动、氛围与人物感受，不为“文学感”堆砌景物。
- **降低 AI 味**：检测模板化情绪、重复句式、过度解释、均匀段落、空泛抒情和常见模型习惯表达，再做局部修订。
- **大纲扩写**：支持从一句章纲 → 场景计划 → 完整章节，而不是直接把大纲“拉长”。
- **长篇记忆**：Story Bible + 人物状态 + 时间线 + 伏笔 + 章节摘要 + 事实账本，按当前章节组装上下文。
- **文风 DNA 融合**：从用户提供的代表文本中提取节奏、句长、对白比例、叙事距离、意象密度、词汇层级等可描述特征，再融合为项目自己的风格配置。
- **多模型可切换**：使用 OpenAI-compatible provider，可接云端 API 或本地模型。

## v0.1 写作流水线

```text
大纲 / Story Bible / 人物卡 / 伏笔 / 前文
                │
                ▼
        Context Assembler
                │
                ▼
       Chapter Scene Planner
                │
                ▼
          Character Gate
                │
                ▼
             Drafter
                │
        ┌───────┴────────┐
        ▼                ▼
 Continuity Critic   Prose Critic
        │                │
        └───────┬────────┘
                ▼
           Local Repair
                │
                ▼
      Save Chapter + Memory
```

## 数据原则

- **GitHub**：代码、治理文件、当前开发状态与决策的权威来源。
- **Google Drive**：用户原始小说资料、参考文本、导出稿、快照等文件保险库。
- API Key / Token 永不写入仓库。
- 参考小说默认不提交正文；系统只保存派生的 style fingerprint / reference signature。

## 快速启动

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

启动后直接在侧栏填写模型的 **Base URL / Model / API Key**。API Key 只用于当前运行会话，不由 Novel 写入项目文件。

## 当前阶段

**Foundation / v0.1**：先把长篇记忆、人物驱动规划、文风 DNA 和去 AI 味审校做成稳定内核，再扩展知识图谱、向量检索、桌面封装和更细的出版工作流。

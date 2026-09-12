# Decision Ledger

## D-001｜本地优先 Web 原型
**Date:** 2026-08-19  
**Status:** ACTIVE

选择 Python + Streamlit 作为 v0.1，而不是先做复杂桌面端或前后端分离。

原因：当前最大风险是写作质量而不是 UI。先用低工程成本验证“人物驱动规划 + 长篇记忆 + Style DNA + 审校”是否真正提升章节质量；若内核成立，再决定 React/Tauri 等产品化路线。

## D-002｜Provider 中立
**Date:** 2026-08-19  
**Status:** ACTIVE

模型调用走 OpenAI-compatible adapter，不把项目绑死在单一模型或供应商。允许后续接 DeepSeek、OpenAI、本地 Ollama / LM Studio 等兼容端点。

## D-003｜文风学习采用 Style DNA，而非作者名提示词
**Date:** 2026-08-19  
**Status:** ACTIVE

代表文本先提取可解释统计特征，再可选用模型抽象高层语义文体特征；多来源按权重融合。参考正文不提交 GitHub，生成后做非可逆 shingle 哈希重合检查。

## D-004｜规划与正文分离
**Date:** 2026-08-19  
**Status:** ACTIVE

章纲先转为场景计划，再写正文。场景计划必须包含目标、阻力、选择、代价和状态变化。原因是“直接扩写大纲”容易产生事件罗列、人物被剧情拖着走和大量过渡性废话。

## D-005｜去 AI 味不是绝对禁词表
**Date:** 2026-08-19  
**Status:** ACTIVE

采用密度、重复、均匀度和编辑审校结合。像“仿佛”“微微”等词允许出现，但连续高密度时才提示，避免把文风修成另一种机械文本。

## D-20260912-CHATGPT｜直接在 ChatGPT 中写作
**Date:** 2026-09-12
**Status:** ACTIVE
**Basis:** 用户明确要求“只用 ChatGPT”，并确认“直接在 ChatGPT 里写作，Novel 仓库保存规则、人物和进度”。

当前产品入口改为 ChatGPT 对话；停止推进本地模型、模型 API 与多模型网站后端。此决定替代 D-001/D-002 的当前实现路线，以及旧 v0.2 分支的 provider/Drive backend 计划；原记录和代码作为历史保留。

复用已有 Story Bible、人物知识边界、场景因果、Style DNA、局部审校与分层记忆设计；把原模型调用顺序改为可审阅的对话阶段。作者确认计划后写作，接受具体正文版本后提取记忆，确认记忆后归档。GitHub 保存规则、人物与结构化进度；正文/参考文本继续按既有存储原则处理。

直接 ChatGPT 写作是用户选择；离线工作台复制/粘贴桥接未被选择，本轮不开发。`docs/CHATGPT_WRITING.md` 是可用协议，`writing/story_state.json` 是空白状态；这不构成新程序、自动 GitHub 同步或小说质量提升的验证结论。

官方资料只用于核对 ChatGPT 项目能够组织聊天、文件、指令和连接来源，不能据此推断具体账号已连接仓库或能自动回写。来源：https://learn.chatgpt.com/docs/projects （2026-09-12 核对）。本次未引入第三方源码。

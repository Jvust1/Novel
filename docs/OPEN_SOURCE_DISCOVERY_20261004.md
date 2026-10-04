# Novel 开源项目候选库（2026-10-04）

> 本文件是 **候选发现清单**，不是默认依赖清单。当前 Novel 的已接入/已登记项目仍以 `governance/open_source_registry.json` 和 `docs/OPEN_SOURCE_INTEGRATION.md` 为准。
>
> 选择原则：先复用能力，再决定是否写代码；先做许可证、维护状态、依赖体积和安全审查；候选必须通过 Novel 的固定长篇 benchmark，才可以进入默认链路。

## 1. 长篇写作工作台与连续性

| 项目 | GitHub | 可借鉴能力 | 建议模式 | 优先级 |
|---|---|---|---|---|
| Novel Studio AI | [YfengJ/novel-studio-ai](https://github.com/YfengJ/novel-studio-ai) | Story Bible、Style Bible、分卷/五章弧、Context Pack、人物状态、关系三元组、连续性检查 | architecture-reference；必要时 adapter | P0 |
| xnovelist | [giapnguyen74/xnovelist](https://github.com/giapnguyen74/xnovelist) | 本地优先编辑器、结构化 Characters/Locations/Style、版本快照、DOCX 导出 | architecture-reference | P1 |
| Story Studio Cloud | [xiangyucao/story-studio-cloud](https://github.com/xiangyucao/story-studio-cloud) | 小说架构、稿件管理、可移植 story-memory JSON、MCP 工作区 | architecture-reference | P1 |
| AeonEchoes | [NekoStash/AeonEchoes](https://github.com/NekoStash/AeonEchoes) | 版本化 Story Bible、叙事知识图谱、多角色规划/写作/连续性 Agent | architecture-reference | P1 |
| NovelForge | [sheengoa/novelforge](https://github.com/sheengoa/novelforge) | 大纲、世界观/人物卡、情节板、偏差日志、下一章闭环 | architecture-reference | P1 |
| NarraLume | [abligail/narralume](https://github.com/abligail/narralume) | Story-memory 搜索、情节预测、影响预览、多格式导入导出 | architecture-reference | P1 |
| Spindle | [VerifiedOrganic/spindle](https://github.com/VerifiedOrganic/spindle) | 本地 MCP 写作服务、场景 writing packet、分支/检查点、连续性和恢复 | external-runtime / MCP adapter | P0 |
| CanonKit | [sadasdfsaf/canonkit](https://github.com/sadasdfsaf/canonkit) | 本地 Story Bible、canon/state/scene context 单一事实源 | architecture-reference | P1 |
| novel-writer-mcp | [novacastriancyber/novel-writer-mcp](https://github.com/novacastriancyber/novel-writer-mcp) | 结构计划、场景 brief、风格指南、连续性检查、Markdown/DOCX/EPUB/PDF 导出 | external-runtime / MCP adapter | P0 |
| novel-writer | [nanbo0ne/novel-writer](https://github.com/nanbo0ne/novel-writer) | 单文件本地工作区、持久记忆、章节桥、可审阅修订 | architecture-reference | P2 |
| Novelist | [AxolDad/novelist](https://github.com/AxolDad/novelist) | SQLite 记忆核心、世界状态、人物关系、并行审稿、自纠错 | architecture-reference | P1 |

**接入结论：** 不复制这些应用的 UI 和整套运行时。Novel 已有 Canon → Active → Recall、计划 → 起草 → 审校 → 修订 → 记忆确认协议；本批项目主要用于补充 schema、MCP 工具边界、分支版本和 context packet 设计。

## 2. 结构化输出与模型可靠性

| 项目 | GitHub | 可借鉴能力 | 建议模式 | 优先级 |
|---|---|---|---|---|
| Instructor | [instructor-ai/instructor](https://github.com/instructor-ai/instructor) | Pydantic 驱动的结构化模型输出、重试和校验 | adapter / research-port | P0 |
| Outlines | [dottxt-ai/outlines](https://github.com/dottxt-ai/outlines) | 本地模型约束生成、JSON/正则/选择集约束 | experiment-candidate | P1 |
| Guardrails AI | [guardrails-ai/guardrails](https://github.com/guardrails-ai/guardrails) | 输出校验、validator、修复与失败报告 | adapter | P1 |
| Guidance | [guidance-ai/guidance](https://github.com/guidance-ai/guidance) | 受控生成与模板化提示 | research-port | P2 |
| JSON Repair | [mangiucode/json_repair](https://github.com/mangiucode/json_repair) | 非严格 JSON 的安全修复信号 | adapter；不能替代 schema 校验 | P1 |
| DSPy | [stanfordnlp/dspy](https://github.com/stanfordnlp/dspy) | 用冻结 benchmark 优化提示程序 | experiment-candidate | P1 |

**门禁：** 结构化输出失败必须阻断记忆写入、Canon 更新和作者接受；不能用“修好了 JSON”代替语义校验。

## 3. MCP 与工具接入

| 项目 | GitHub | 可借鉴能力 | 建议模式 | 优先级 |
|---|---|---|---|---|
| MCP Python SDK | [modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk) | 标准化资源、工具、提示与服务器协议 | external-runtime / adapter | P0 |
| FastMCP | [PrefectHQ/fastmcp](https://github.com/PrefectHQ/fastmcp) | Python MCP 服务快速封装、类型化工具和资源 | external-runtime | P1 |
| MCP Inspector | [modelcontextprotocol/inspector](https://github.com/modelcontextprotocol/inspector) | MCP 工具调试和交互检查 | external-tool | P1 |
| mcp-use | [mcp-use/mcp-use](https://github.com/mcp-use/mcp-use) | MCP 客户端和 Agent 连接模式 | experiment-candidate | P2 |

**接入结论：** 先把 Novel 的读取、计划、审校、保存回执做成最小只读/候选写入 MCP 工具；作者接受仍由 Novel 协议控制，不能交给通用 Agent 自动确认。

## 4. 本地模型与推理运行时

| 项目 | GitHub | 可借鉴能力 | 建议模式 | 优先级 |
|---|---|---|---|---|
| llama.cpp | [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp) | GGUF 本地推理、CPU/GPU 量化、OpenAI 兼容服务 | external-runtime | P0 |
| Ollama | [ollama/ollama](https://github.com/ollama/ollama) | 本地模型拉取和 HTTP 服务 | external-runtime（现有登记） | P0 |
| vLLM | [vllm-project/vllm](https://github.com/vllm-project/vllm) | GPU 高吞吐 OpenAI 兼容服务 | external-runtime（现有登记） | P1 |
| KoboldCpp | [LostRuins/koboldcpp](https://github.com/LostRuins/koboldcpp) | GGUF 本地推理与长文本服务 | external-runtime；AGPL 复核 | P2 |
| LocalAI | [mudler/LocalAI](https://github.com/mudler/LocalAI) | 多模型本地 OpenAI 兼容层 | external-runtime | P2 |

**接入结论：** Novel 只依赖 Provider 接口，不把模型二进制、CUDA、量化运行时纳入仓库。

## 5. 评测、追踪与回归

| 项目 | GitHub | 可借鉴能力 | 建议模式 | 优先级 |
|---|---|---|---|---|
| promptfoo | [promptfoo/promptfoo](https://github.com/promptfoo/promptfoo) | Prompt/模型矩阵、CI 回归、红队检查 | external-tool（现有登记） | P0 |
| DeepEval | [confident-ai/deepeval](https://github.com/confident-ai/deepeval) | LLM-as-a-judge、幻觉、相关性、任务完成度指标 | adapter（现有登记） | P0 |
| Ragas | [vibrantlabsai/ragas](https://github.com/vibrantlabsai/ragas) | RAG/Recall 指标 | adapter（现有登记） | P1 |
| OpenLLMetry | [traceloop/openllmetry](https://github.com/traceloop/openllmetry) | LLM trace 和 OpenTelemetry 观测 | adapter | P1 |
| Phoenix | [Arize-ai/phoenix](https://github.com/Arize-ai/phoenix) | 本地/自托管追踪、检索和评测可视化 | external-runtime | P2 |
| OpenTelemetry Python | [open-telemetry/opentelemetry-python](https://github.com/open-telemetry/opentelemetry-python) | 生成、召回、审校的统一 trace | adapter | P1 |
| Hypothesis | [HypothesisWorks/hypothesis](https://github.com/HypothesisWorks/hypothesis) | Schema、状态机和边界条件属性测试 | dev-only | P1 |
| pytest-xdist | [pytest-dev/pytest-xdist](https://github.com/pytest-dev/pytest-xdist) | 大型固定回归并行执行 | dev-only | P2 |

**评测门禁：** 组件只有在固定合成故事和真实章节样例上同时改善事实召回、知识边界、连续性、语言自然度或原创风险，才可升为默认；人类盲评仍是文学质量最终依据。

## 6. 文档解析、中文质量与安全

| 项目 | GitHub | 可借鉴能力 | 建议模式 | 优先级 |
|---|---|---|---|---|
| Apache Tika | [apache/tika](https://github.com/apache/tika) | 多格式文本和元数据提取 | external-runtime / adapter | P2 |
| Microsoft Presidio | [microsoft/presidio](https://github.com/microsoft/presidio) | PII 检测和脱敏，防止密钥/个人数据进入日志 | adapter | P1 |
| Semgrep | [semgrep/semgrep](https://github.com/semgrep/semgrep) | Python/配置安全规则与自定义扫描 | dev-only | P1 |
| Ruff | [astral-sh/ruff](https://github.com/astral-sh/ruff) | 快速 lint/format/import 检查 | dev-only（现有 CI 可复用） | P1 |
| Bandit | [PyCQA/bandit](https://github.com/PyCQA/bandit) | Python 安全静态检查 | dev-only（现有 CI 可复用） | P1 |
| OpenCC | [BYVoid/OpenCC](https://github.com/BYVoid/OpenCC) | 简繁与词汇规范化 | direct-optional（现有登记） | P0 |
| HanLP | [hankcs/HanLP](https://github.com/hankcs/HanLP) | 中文分词、NER、词性 | direct-optional（现有登记） | P1 |
| pycorrector | [shibing624/pycorrector](https://github.com/shibing624/pycorrector) | 错别字和语病诊断 | adapter（现有登记） | P0 |

## 7. 只作研究参考的项目

以下项目适合观察产品交互或算法思路，不能因为“功能看起来完整”就直接复制：

- [novelWriter](https://github.com/vkbo/novelWriter)：成熟的长篇写作组织方式。
- [Kindling](https://github.com/smith-and-web/kindling)：章节、场景、结构模板与导入流程。
- [Novalist](https://github.com/Drommedhar/novalist)：离线优先写作和故事图；仓库状态需先确认，不能按默认依赖处理。
- [SillyTavern](https://github.com/SillyTavern/SillyTavern)：World Info/Lorebook 上下文 UX；AGPL 只作外部参考。
- [KoboldCpp](https://github.com/LostRuins/koboldcpp)：外部本地运行时；许可证和部署边界单独复核。
- 无许可证或许可证不清楚的项目：只记录架构观察，不复制源代码、不作为依赖。

## 8. 分阶段落地顺序

1. **P0 低风险能力**：Instructor 或现有 Pydantic 强化、MCP 只读工具、llama.cpp/Ollama 外部 provider、pycorrector/OpenCC、promptfoo/DeepEval 固定回归。
2. **P1 结构增强**：Spindle/novel-writer-mcp 的 context packet 和检查点思想；OpenTelemetry trace；Presidio 日志脱敏；Hypothesis 状态机测试。
3. **P1 实验能力**：Outlines/Guardrails 结构化生成、GraphRAG/LightRAG/Graphiti 等召回后端，全部挂在 A/B 开关后。
4. **P2 研究能力**：DSPy、Phoenix、文档解析备用链路和其它完整写作工作台，仅在 benchmark 有明确收益时采用。

## 9. 许可证与采用记录要求

每个真正采用的项目必须补充到 `governance/open_source_registry.json`，至少记录：

- 仓库、commit/tag、许可证和检查日期；
- `direct-optional`、`adapter`、`research-port`、`external-runtime` 或 `architecture-reference-only`；
- Novel 内部接口、测试覆盖和回滚方式；
- 是否进入默认安装、是否需要额外服务；
- 上游源码或算法片段的 provenance 和 NOTICE；
- 固定 benchmark 的前后结果。

本次候选发现不改变默认依赖、不上传私人小说、不把候选项目源码复制进 Novel。

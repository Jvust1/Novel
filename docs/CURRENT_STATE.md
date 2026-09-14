# Current State

## 2026-09-14（第三轮）

CI 修复 + 评测闭环补全 + 参考文本格式扩展。测试 27 项全部通过（含 bare `pytest`）。

### 本轮内容

- **CI 修复（blocking）**：main 上 run 34797893235 失败——workflow 用 bare `pytest`，不把仓库根加入 `sys.path`。新增 `pyproject.toml`（`[tool.pytest.ini_options] pythonpath=["."]`），本地 bare pytest 验证通过；**修复尚未推送**，推送后 CI 才会变绿。
- `scripts/aggregate_scores.py`：评分表聚合 CLI——读取填好的 `scoring_sheet.csv`，按 run.json 的 case/variant 网格检查覆盖缺口（缺哪些维度、哪些组整组未评），输出聚合 JSON（含 B−A delta），`--write` 落盘 `scores_summary.json` 供回填 ledger。
- `novel_ai/reading.py`：参考文本导入扩展到 DOCX（python-docx）与 PDF（pypdf），懒加载依赖；app.py Style Lab 上传器已支持四种格式。
- `project_state.json`：repository 更正为 `Jvust2/Novel`（远端实际地址）。

## 2026-09-14（第二轮）

v0.2 评测骨架：冻结基准 novel-ab-v1 + A/B 运行器（E-001，状态 PENDING_RUN）。

### 本轮新增

- `benchmarks/`：三个原创冻结用例（urban_dispute / xuanhuan_residual / mystery_calls），各含 Bible、人物卡（知识边界）、章纲、目标与三轮前情；`benchmark_manifest.json` 记录 SHA-256，加载与测试强制校验，改动即报错。
- `novel_ai/eval.py`：12 维评分 rubric（E-000 口径）、变体定义（A_baseline / B_memory 单变量对照）、`run_case` / `run_benchmark`（结果写入不可变 `runs/<run_id>/`，gitignore）、评分表生成 / 读取 / 聚合（含 B−A delta）。
- `scripts/run_benchmark.py`：CLI；密钥只从 `NOVEL_BASE_URL / NOVEL_MODEL / NOVEL_API_KEY` 环境变量读取，不落盘。
- 测试增至 19 项，全部通过（含冻结哈希防篡改、变体唯一差异、评分表 roundtrip）。

### 阻塞点

真实 A/B 运行需要模型端点。运行命令与评分流程见 `benchmarks/README.md`。

## 2026-09-14

v0.2：补齐长篇记忆内核（A2 的 Memory Update 环节 + A4 的三层记忆）。

### 本轮新增

- `novel_ai/models.py`：`MemoryExtraction` / `CharacterMemoryUpdate` / `TimelineEvent` / `ForeshadowItem` Schema。
- `novel_ai/prompts.py`：章节后记忆抽取协议；plan/draft 支持 `extra_context` 注入长期记忆。
- `novel_ai/memory.py`：`apply_extraction` 纯函数回写——知识边界一致性（获得知识移出 does_not_know、澄清误解移出 false_beliefs）、事实/线索/伏笔去重、幂等、未知人物拦截进 `unapplied_updates`。
- `novel_ai/context.py`：`ContextAssembler` 按预算组装 Canon（锁定事实+未回收线索）/ Active（开放伏笔+近章摘要）/ Recall（更早章节一行回顾），resolved 伏笔不进入 Active。
- `novel_ai/storage.py`：`save_extraction` / `load_story_state` / `save_story_state` / `all_chapter_summaries`。
- `novel_ai/engine.py`：`extract_memory()`；plan/draft/run 透传 `extra_context`。
- `app.py`：生成时自动组装三层上下文；新增"抽取本章记忆并回写"按钮与 story_state 查看器。
- 测试 12 项全部通过（memory 回写幂等/知识边界/伏笔状态推进；context 分层与预算）。

### 设计要点

- 回写逻辑全部在代码侧，模型只负责抽取（D-006）；模型输出不直接改人物卡。
- 仍不引入向量 RAG / 知识图谱，等真实 A/B 评测结果（D-007）。

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

- 人物、事件、伏笔在章节生成后尚未自动回写结构化状态。（2026-09-14 已解决：`novel_ai/memory.py`）
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

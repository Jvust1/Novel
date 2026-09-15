# Current State

## 2026-09-15（第三轮）

基线对齐检查（PROJECT_NORTH_STAR / PRODUCT_SPEC）后补上工作台的计划确认流程。

### 发现与修复

- **缺口**：North Star 第 7 条与 Product Spec UX 原则都要求"AI 先给结构化建议，用户可编辑，再生成正文"，但 write_tab 是"生成本章"一键到底，场景计划从未给用户确认机会。
- **修复**：写作流程改为默认两步——① 生成场景计划 → 计划以可编辑 JSON 呈现（改目标、阻力、选择、代价、知识边界）→ ② 按确认后的计划写正文（计划与正文共用同一份组装上下文，保证一致性）；保留"一步生成"作为快速路径。② 在没有确认计划时禁用。
- 测试 39 项全过（新增 AppTest 门控测试：无计划时 ② 禁用、编辑器不出现；注入计划后启用且内容正确）。

## 2026-09-15（第二轮）

Review → Repair 闭环真实验证 + 一个真实环境缺陷修复。测试 38 项全过。

### 本轮内容

- **系统代理劫持本地端点（已修复）**：httpx ≥0.28 会读取 Windows 注册表系统代理；本机代理（127.0.0.1:10809）拒绝转发 loopback 目标，对本地 Ollama 的调用全部变成空体 503（curl 不读注册表所以对照正常；昨天 benchmark 成功是因为当时系统代理未开）。修复：`provider.is_loopback_url` 检测 loopback 端点并对其实例化 `httpx.Client(trust_env=False)`；远程端点保持 trust_env（云端 API 仍可走用户代理）。回归测试 3 项（loopback 判定、本地禁代理、远程保留代理）。
- **Review → Repair 真实验证**（urban_dispute B 变体 + 真实 plan，qwen3-vl:4b）：审校返回合法 JSON；verdict=pass 时修复稿与原稿相似度 98.92%——局部修复纪律在"通过"场景下不重写整章，行为正确。
- **观察（4B 审校者过宽）**：该章存在人工可辨的连续性瑕疵（E-001 已记录的伤势描述不符），4B 审校却给 pass 零问题——审校角色需要更强模型，正好验证了 D-008 角色路由（REVIEW 走独立端点）的架构价值；待有第二个端点后在 UI/评测中启用。
- 至此流水线五环节（Context → Plan → Draft → Review → Memory Update）全部经过真实模型执行验证。

## 2026-09-15

## 2026-09-15

工作台状态回载 + 评分辅助工具。测试 35 项全过（新增 Streamlit `AppTest` 应用级执行测试）。

### 本轮新增

- **工作台状态回载（可用性修复）**：app.py 新增 `seed_project_state`——按当前项目从 `memory/story_bible.json`、`outline.json`、`characters.json`、`styles/*.json` 回载设定、人物、Style DNA 与参考签名；此前重启应用虽已落盘但从不回载。策略是非破坏的：只回载已保存的数据，未保存项目保留会话现状。
- **应用级测试**：`tests/test_app.py` 用 `streamlit.testing.v1.AppTest` 真正执行 app.py（此前的 health 冒烟只验证服务器不执行脚本）——覆盖启动无异常与回载正确性。
- **评分包渲染**：`novel_ai/eval.py:render_scoring_pack` + `scripts/render_scoring_pack.py`——从 run 目录生成 `scoring_pack.md`（每用例目标/要求 + A/B 双变体全文 + 12 维锚点表），`run-20260914-153013` 已生成，供人工评分时对照。
- Ollama 服务进程曾退出（机器重启）；qwen2.5:7b 下载已按用户要求取消，第二轮评测搁置，待评分或新端点。

### 记忆回写环节真实模型验证（2026-09-15，未入库的本地验证）

用本地 qwen3-vl:4b 对 `run-20260914-153013/urban_dispute__B_memory.txt` 完整跑通 `extract_memory → apply_extraction`：

- 抽取结果符合 Schema；三个角色更新全部命中人物卡姓名（`unapplied_updates` 为空）。
- 回写正确：knows 追加、`recent_change` 带 `[004B]` 章节戳、status 合并无丢失。
- **发现抽取器的一个真实缺陷模式**：模型把疑似读者视角信息（周凯藏钥匙）写进了陈桂香的 `knowledge_gained`——"人物知道 vs 读者知道"的区分对 4B 模型不可靠。改进方向（未实施）：抽取协议中加入"逐条知识归属检查"示例，或在审校协议中增加知识来源复核项；待人工评分确认该问题权重后再动。
- 验证时 story_state 从空开始（未带前情伏笔），故模型新建了伏笔条目而非推进已有 `zhou-key`——正式流程会传入累积 state，此为验证设置差异，非代码缺陷。

## 2026-09-14（第四轮）

回收过期 dev 分支的多模型路由能力（D-008）。

### 盘点结论（只读）

远端 `dev/multi-model-drive-backend-v0-2` 停在 2026-08-24，基线远落后 main；整体合并会删除 main 的记忆/评测子系统（diff 约 -2100 行）。其有价值部分：ProviderRouter（TaskKind 角色回退路由：draft/plan/review/memory/benchmark）、RoutedNovelEngine（writer/reviewer 分离）、离线路由测试。分支保留原样，未动。

### 本轮新增（additive 移植）

- `novel_ai/orchestration.py`：原样移植（仅依赖 provider.py，无冲突）。
- `novel_ai/routed_engine.py`：移植并适配 main 的 `extra_context` 参数透传。
- 测试 +5（含 writer/reviewer 角色分离与 reviewer 缺失回退），共 32 项全过。
- 未接线：app.py 与 eval 尚未暴露路由模式；待真实端点出现后再决定 UI/评测入口（避免无端点的死配置）。
- dev 分支记录的 Ollama 前置问题（qwen3:4b，`could not locate ollama app`，安装/PATH 问题）仍待用户本机解决。

## 2026-09-14（第三轮）

CI 修复 + 评测闭环补全 + 参考文本格式扩展。测试 27 项全部通过（含 bare `pytest`）。

### 本轮内容

- **CI 修复（blocking）**：main 上 run 34797893235 失败——workflow 用 bare `pytest`，不把仓库根加入 `sys.path`。新增 `pyproject.toml`（`[tool.pytest.ini_options] pythonpath=["."]`）；修复已在 PR #4 的 CI run 34828564029 上验证通过（经授权合并后 main CI 恢复绿色）。
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

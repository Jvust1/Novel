# AGENTS.md

任何 GPT / Claude / Codex / DeepSeek / 本地 Agent 接手 Novel 前，按以下顺序恢复状态。

## 1. 全项目基线

先读取 Google Drive 根目录：

`00_全项目总入口_新AI先读此文件`

然后按入口文件要求动态读取根目录所有 `全项目_` 基线文件。不得只依赖聊天记忆。

## 2. Novel 仓库必读顺序

1. `governance/project_state.json`
2. `docs/PROJECT_NORTH_STAR.md`
3. `docs/ARCHITECTURE_INVARIANTS.md`
4. `docs/CURRENT_STATE.md`
5. `docs/DECISION_LEDGER.md`
6. `docs/EVALUATION_LEDGER.md`
7. `governance/artifact_manifest.json`
8. `docs/PRE_FLIGHT_CHECKLIST.md`
9. `docs/HANDOFF.md`

## 3. 不可绕过的写作原则

- 先理解大纲与人物，再生成正文。
- 长篇一致性依赖结构化状态，不依赖“把整本书塞进上下文”。
- 情节推进必须能解释为人物目标、选择、阻力和后果，不得频繁依靠作者强行安排。
- 环境描写只在其影响行动、情绪、信息、节奏或场景辨识度时进入正文；避免为“文学感”堆砌景物。
- 允许留白、冷句、短句和不解释；不要把每个动作后面都接情绪说明。
- 对话必须具有角色差异、目的、遮掩或关系张力，避免全员同一种“聪明 AI 口吻”。
- 人物只能使用其已经获得的信息；秘密、误解和知识边界属于硬约束。
- 每次生成后检查人物状态、时间线、伏笔和事实是否需要更新。

## 4. 文风规则

- 用户提供的代表小说可用于提取高层、可描述的文体特征：句长与波动、段落节奏、对白比例、叙事距离、视角稳定性、动作/心理/环境配比、意象密度、词汇层级、修辞偏好等。
- 系统目标是形成项目自己的“Style DNA”，可以多来源加权融合。
- 不把某位作者名字当作唯一风格指令，不追求逐句仿写。
- 参考文本默认不提交到 GitHub；只提交派生特征、哈希签名和用户明确允许保存的摘要。
- 生成内容需要做近似复用/长片段重合检查，避免把参考文本变成改写素材库。

## 5. 数据与安全

- API Key、Token、Cookie、密码、私密环境变量不得进入 GitHub / Drive 正文文件。
- 原始小说、参考书、PDF、DOCX、TXT 等大文件按 Drive 项目归档规则保存。
- GitHub 是项目开发状态和治理的权威来源；Drive 是原始文件与产物保险库。
- 若同步失败，写入 `pending_sync` 并明确 blocking / non_blocking。

## 6. 修改纪律

任何会改变项目目标、架构、写作协议、状态 Schema、生成流水线、评测方法或下一步的实质变化，都必须同步更新治理文件。不要让聊天成为唯一记录。

## 7. Artifact synchronization — mandatory deduplication

当用户说“更新成果”“同步所有成果”“更新 GitHub 和 Drive”“归档全部成果”或同义表达时，必须遵循 `docs/ARTIFACT_SYNC_POLICY.md`，不得解释为盲目全量重传。

- 先盘点工作区、本仓库目标分支和 Novel 对应 Drive 项目目录，再进行任何写入。
- GitHub 同路径内容相同直接 `SKIP_IDENTICAL`；仅 CRLF/LF 或末尾换行差异不得制造新提交。
- Drive 比较目标目录、文件名、大小和 SHA-256；完全相同则复用原 Drive ID，不重新上传。
- 同一逻辑文件发生实质变化时优先原位更新；只有真正的新成果才新建对象。
- `r1/r2/r3`、run ID、时间戳、freeze、replay、calibration 等具有独立审计身份的历史成果，即使字节相同也默认保留为 `HISTORICAL_DUPLICATE_PRESERVED`。
- 一次逻辑同步使用最少实际需要的 GitHub commits；禁止一文件一提交式全量发布。
- 完成后报告 `NEW / CHANGED / SKIP_IDENTICAL / HISTORICAL_DUPLICATE_PRESERVED / CONFLICT_NEEDS_REVIEW` 计数，以及 GitHub commit、Drive 新建/原位更新数量。
- 同样输入连续执行两次，第二次必须产生 **0 个 GitHub 新提交、0 个 Drive 新对象**。
- 不得因内容重复而自动删除历史快照、冻结证据或具有独立 provenance 的版本。

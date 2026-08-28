# v0.2 多模型网站后端架构

## 目标

在不改变 Novel 现有 Context → Scene Plan → Draft → Review → Repair → Memory Update 核心流水线的前提下，增加统一后端编排层：

- 前端网站只调用后端，不直接接触模型或 Google Drive。
- 本地模型负责低延迟写作、规划和记忆提取。
- Colab 作为批量实验和临时算力节点。
- V4 API 作为可替换的高质量生成节点。
- GPT 作为独立审校节点。
- Google Drive 保存章节草稿、审核结果、章节记忆和快照。
- GitHub 只保存代码、治理、Schema 和派生统计，不保存小说正文。

## 路由策略

| 任务 | 首选 | 回退 |
|---|---|---|
| draft / plan | local | v4 → colab |
| review | reviewer | local → v4 |
| memory | local | colab → v4 |
| benchmark | colab | local → v4 |

所有模型均通过 OpenAI-compatible /chat/completions 接口调用。路由层不保存密钥。

## 运行时变量

    NOVEL_LOCAL_BASE_URL
    NOVEL_LOCAL_MODEL
    NOVEL_LOCAL_API_KEY

    NOVEL_COLAB_BASE_URL
    NOVEL_COLAB_MODEL
    NOVEL_COLAB_API_KEY

    NOVEL_V4_BASE_URL
    NOVEL_V4_MODEL
    NOVEL_V4_API_KEY

    NOVEL_REVIEW_BASE_URL
    NOVEL_REVIEW_MODEL
    NOVEL_REVIEW_API_KEY

    NOVEL_DRIVE_ACCESS_TOKEN
    NOVEL_DRIVE_ROOT_FOLDER_ID=135EL_t49i-Xyhncd9ZIukQg7_y27cEf-

所有模型权重和大型缓存遵守全项目规则，放在 D 盘；Ollama 默认目录为 D:\OllamaModels。

## Drive 草稿结构

以现有 Novel 文件夹为根：

- 01_Raw_Uploads
- 02_Generated_Artifacts
- 03_Experiment_Results
- 04_Snapshots
- 05_Reference_Materials
- 06_GitHub_Project

章节建议按项目和章节拆分：

    02_Generated_Artifacts/<project>/chapters/001.md
    02_Generated_Artifacts/<project>/reviews/001.json
    02_Generated_Artifacts/<project>/memory/001.json

不要把整本小说存成单一可编辑文件；正文文件、审核文件、记忆文件分别版本化，便于回退和人工确认。

## 当前阶段

本次先提交 provider router、Drive 存储适配器和无网络单元测试。下一步再把 Streamlit 页面改成网站入口，并接入 OAuth / 登录会话和章节接受门。

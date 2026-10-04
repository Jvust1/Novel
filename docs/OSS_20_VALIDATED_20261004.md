# Novel / 20 个高星开源项目（GitHub 高星项目核验清单）

> 快照日期：2026-10-04。星标、默认分支、许可证来自 GitHub 仓库元数据；候选阈值为星标 ≥ 1,000，当前 Novel 已有 47 项上游登记，本文件给出本轮逐项元数据核验的 20 项优先集合。

## 集成规则

- “纳入”表示候选已登记；代码采用项目自有适配器/协议，不复制上游整库。
- MIT、Apache-2.0、BSD、ISC、MPL 进入可审查适配集合；GPL、AGPL、NOASSERTION 只进入隔离或参考路径。
- 真实数据、模型权重、素材和服务条款另行核验；默认链路保持可回滚。

## 20 个项目

| # | 项目 | 星标 | 许可证 | 主要能力 | 本仓库接入方式 |
|---:|---|---:|---|---|---|
| 1 | [langchain-ai/langchain](https://github.com/langchain-ai/langchain) | 147,437 | MIT | 链式编排与工具调用 | `adapter` |
| 2 | [run-llama/llama_index](https://github.com/run-llama/llama_index) | 52,408 | MIT | 文档索引与检索编排 | `adapter` |
| 3 | [deepset-ai/haystack](https://github.com/deepset-ai/haystack) | 26,650 | Apache-2.0 | 可解释 RAG pipeline | `adapter` |
| 4 | [huggingface/transformers](https://github.com/huggingface/transformers) | 166,951 | Apache-2.0 | 本地模型与生成 | `external-runtime` |
| 5 | [vllm-project/vllm](https://github.com/vllm-project/vllm) | 93,170 | Apache-2.0 | 高吞吐推理服务 | `external-runtime` |
| 6 | [openai/openai-python](https://github.com/openai/openai-python) | 31,744 | Apache-2.0 | OpenAI-compatible provider | `adapter` |
| 7 | [pydantic/pydantic](https://github.com/pydantic/pydantic) | 28,939 | MIT | 结构化状态与响应校验 | `adapter` |
| 8 | [explosion/spaCy](https://github.com/explosion/spaCy) | 33,937 | MIT | 实体与句法分析 | `optional-adapter` |
| 9 | [FlagOpen/FlagEmbedding](https://github.com/FlagOpen/FlagEmbedding) | 12,212 | MIT | 向量与重排 | `optional-adapter` |
| 10 | [huggingface/sentence-transformers](https://github.com/huggingface/sentence-transformers) | 19,150 | Apache-2.0 | 本地 embedding 回退 | `optional-adapter` |
| 11 | [qdrant/qdrant](https://github.com/qdrant/qdrant) | 34,930 | Apache-2.0 | 向量检索后端 | `external-runtime` |
| 12 | [chroma-core/chroma](https://github.com/chroma-core/chroma) | 29,437 | Apache-2.0 | 轻量本地向量库 | `external-runtime` |
| 13 | [milvus-io/milvus](https://github.com/milvus-io/milvus) | 46,317 | Apache-2.0 | 规模化向量库 | `external-runtime` |
| 14 | [openai/tiktoken](https://github.com/openai/tiktoken) | 19,380 | MIT | 上下文预算与 token 计数 | `optional-adapter` |
| 15 | [fxsjy/jieba](https://github.com/fxsjy/jieba) | 35,176 | MIT | 中文分词 | `optional-adapter` |
| 16 | [rapidfuzz/RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) | 4,149 | MIT | 实体近似匹配 | `optional-adapter` |
| 17 | [BYVoid/OpenCC](https://github.com/BYVoid/OpenCC) | 10,027 | Apache-2.0 | 中文繁简规范化 | `optional-adapter` |
| 18 | [shibing624/pycorrector](https://github.com/shibing624/pycorrector) | 6,529 | Apache-2.0 | 错别字与语病提示 | `optional-adapter` |
| 19 | [adbar/trafilatura](https://github.com/adbar/trafilatura) | 6,909 | Apache-2.0 | 网页正文抽取 | `optional-adapter` |
| 20 | [docling-project/docling](https://github.com/docling-project/docling) | 68,374 | MIT | PDF/DOCX 结构化导入 | `optional-adapter` |

## 当前代码落点

- `novel_ai/oss_batch_20261004.py` / `invest/oss_batch_20261004.py` 提供无副作用的注册表、许可证过滤和可选模块探测。
- 注册表不会自动安装依赖；`available_projects()` 只报告当前环境已经存在的包。
- 每一项都保留 upstream URL、星标快照和许可证字段，便于后续升级或撤回。

## 审查结论

本批次以薄适配层为主，便于在现有测试门后逐项启用；未通过许可证或业务验证的项目不会进入默认运行路径。

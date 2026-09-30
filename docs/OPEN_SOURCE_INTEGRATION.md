# Novel Open-Source Integration Map

> Updated: 2026-09-27  
> Scope: public GitHub projects that materially help Novel reach the Reference Pack → Style DNA + Story DNA → original long-form generation → human-feel/originality/evaluation target.

## Integration policy

Novel **does not** bulk-copy arbitrary repositories. "纳入" means one of four controlled modes:

- **direct-optional / adapter** — install an upstream package and call it behind a Novel-owned interface.
- **research-port** — absorb an algorithmic idea into Novel's existing deterministic architecture, with our own implementation/tests.
- **experiment-candidate** — available behind an A/B gate; it must beat the current baseline before becoming default.
- **external-runtime / external-tool** — run separately and connect via API/CLI.
- **architecture-reference-only** — inspect ideas only; no source copying (used for no-license or copyleft projects where vendoring is undesirable).
- **git-submodule** — pin a compatible upstream source tree at a reviewed commit while preserving upstream license/history.

This preserves the project's current invariants: provider-neutral, local-first, structured memory, reproducible benchmarks, and no raw reference novels in GitHub.

## What is already wired in this round

1. `novel_ai/integrations.py` — machine-readable capability registry + install probes.
2. `novel_ai/reference_pack.py` — multi-reference pack builder; stores derived style/provenance/signatures but never source prose.
3. `novel_ai/semantic.py` — dependency-free Chinese char-ngram similarity plus adapters for text2vec and FlagEmbedding.
4. `scripts/build_reference_pack.py` — CLI to build a Reference Pack from TXT/MD/DOCX/PDF.
5. `scripts/check_integrations.py` — reports which optional integrations are installed.
6. `requirements-extras/*` — heavy dependencies split by capability so the default install stays small.
7. `governance/open_source_registry.json` — auditable upstream registry.

## Upstream registry (47 projects)

| Priority | Key | Upstream | License | Adoption mode | Novel use |
|---|---|---|---|---|---|
| P1 | `re3` | [yangkevin2/emnlp22-re3-story-generation](https://github.com/yangkevin2/emnlp22-re3-story-generation) | MIT | research-port | 递归 reprompt + revision；用于长篇生成/修订实验 |
| P0 | `doc_story` | [yangkevin2/doc-story-generation](https://github.com/yangkevin2/doc-story-generation) | MIT | research-port | 详细大纲控制；吸收到 Story Forge 的层级规划 |
| P0 | `doc_story_v2` | [facebookresearch/doc-storygen-v2](https://github.com/facebookresearch/doc-storygen-v2) | Apache-2.0 | research-port | Premise→Plan→Story 现代化实现；作为 Story DNA/长篇生成骨架参考 |
| P1 | `chinese_novelist_skill` | [PenglongHuang/chinese-novelist-skill](https://github.com/PenglongHuang/chinese-novelist-skill) | MIT | research-port | 中文小说问答、偏好记忆、断点续写与校验流程 |
| P1 | `spacy` | [explosion/spaCy](https://github.com/explosion/spaCy) | MIT | git-submodule | 成熟 NLP pipeline；结构/实体/句法/风格特征分析 |
| P0 | `pycorrector` | [shibing624/pycorrector](https://github.com/shibing624/pycorrector) | Apache-2.0 | git-submodule | 中文错别字/语病诊断与局部修订信号 |
| P1 | `texthero` | [jbesomi/texthero](https://github.com/jbesomi/texthero) | MIT | git-submodule | 文本清洗、向量化和探索分析 |
| P0 | `opencc` | [BYVoid/OpenCC](https://github.com/BYVoid/OpenCC) | Apache-2.0 | git-submodule | 中文简繁/词汇规范统一 |
| P0 | `lexicalrichness` | [LSYS/LexicalRichness](https://github.com/LSYS/LexicalRichness) | MIT | git-submodule | 词汇丰富度、重复度和词汇变化诊断 |
| P1 | `textstat` | [textstat/textstat](https://github.com/textstat/textstat) | MIT | git-submodule | 可读性与句子复杂度统计 |
| P1 | `proselint` | [amperser/proselint](https://github.com/amperser/proselint) | BSD-3-Clause | git-submodule | prose lint；英文规则为主，只作可选/参考层 |
| P0 | `pkuseg` | [lancopku/pkuseg-python](https://github.com/lancopku/pkuseg-python) | MIT | git-submodule | 中文分词，为风格与重复分析提供稳定切分 |
| P0 | `book_to_skill` | [virgiliojr94/book-to-skill](https://github.com/virgiliojr94/book-to-skill) | MIT | git-submodule | 把参考书/文档转换为按需加载的 Agent Skill，为 Reference Pack / Story DNA 提供结构化知识层 |
| P2 | `booknlp` | [booknlp/booknlp](https://github.com/booknlp/booknlp) | MIT | research-port | 人物/对白/叙事分析思想；英文中心，不作为中文默认后端 |
| P1 | `hanlp` | [hankcs/HanLP](https://github.com/hankcs/HanLP) | Apache-2.0 | direct-optional | 中文分词、词性、NER 等深层文本特征 |
| P0 | `jieba` | [fxsjy/jieba](https://github.com/fxsjy/jieba) | MIT | direct-optional | 轻量中文分词与 Reference Pack 词汇统计 |
| P0 | `text2vec` | [shibing624/text2vec](https://github.com/shibing624/text2vec) | Apache-2.0 | adapter | 中文语义向量、相似度、原创性/Recall 检索 |
| P0 | `flagembedding` | [FlagOpen/FlagEmbedding](https://github.com/FlagOpen/FlagEmbedding) | MIT | adapter | BGE 向量/重排器；Reference similarity 与 Recall |
| P1 | `sentence_transformers` | [huggingface/sentence-transformers](https://github.com/huggingface/sentence-transformers) | Apache-2.0 | adapter | 通用 embedding 备选 |
| P0 | `rapidfuzz` | [rapidfuzz/RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) | MIT | direct-optional | 人名/短语/事件摘要近似匹配与去重 |
| P0 | `docling` | [docling-project/docling](https://github.com/docling-project/docling) | MIT | adapter | 复杂 PDF/DOCX/版面解析，增强参考小说导入 |
| P1 | `markitdown` | [microsoft/markitdown](https://github.com/microsoft/markitdown) | MIT | adapter | 多文档统一转 Markdown |
| P2 | `unstructured` | [Unstructured-IO/unstructured](https://github.com/Unstructured-IO/unstructured) | Apache-2.0 | adapter | 文档 partition/metadata 备用路径 |
| P1 | `graphrag` | [microsoft/graphrag](https://github.com/microsoft/graphrag) | MIT | experiment-candidate | 全局/局部图检索；仅在 A/B 证明收益后启用 |
| P1 | `lightrag` | [HKUDS/LightRAG](https://github.com/HKUDS/LightRAG) | MIT | experiment-candidate | 轻量图+向量 Recall |
| P1 | `hipporag` | [OSU-NLP-Group/HippoRAG](https://github.com/OSU-NLP-Group/HippoRAG) | MIT | experiment-candidate | 关联式检索，适合长篇跨章关系回忆实验 |
| P2 | `mem0` | [mem0ai/mem0](https://github.com/mem0ai/mem0) | Apache-2.0 | experiment-candidate | 记忆抽取/检索模式参考 |
| P1 | `graphiti` | [getzep/graphiti](https://github.com/getzep/graphiti) | Apache-2.0 | experiment-candidate | 带时间维度的知识图谱；适合人物/事件历史 |
| P2 | `llama_index` | [run-llama/llama_index](https://github.com/run-llama/llama_index) | MIT | experiment-candidate | 索引/检索抽象，不替换 Novel 核心管线 |
| P2 | `langchain` | [langchain-ai/langchain](https://github.com/langchain-ai/langchain) | MIT | experiment-candidate | 外部工具和 retriever 接入模式 |
| P2 | `haystack` | [deepset-ai/haystack](https://github.com/deepset-ai/haystack) | Apache-2.0 | experiment-candidate | 可组合 pipeline 组件模式 |
| P2 | `chroma` | [chroma-core/chroma](https://github.com/chroma-core/chroma) | Apache-2.0 | experiment-candidate | 本地向量库候选 |
| P1 | `qdrant` | [qdrant/qdrant](https://github.com/qdrant/qdrant) | Apache-2.0 | experiment-candidate | 长篇项目向量库候选 |
| P1 | `litellm` | [BerriAI/litellm](https://github.com/BerriAI/litellm) | MIT-core | adapter | 统一多模型 Provider；企业目录不纳入 |
| P0 | `ollama` | [ollama/ollama](https://github.com/ollama/ollama) | MIT | external-runtime | 本地模型运行时；Novel 已兼容 OpenAI-like 端点 |
| P1 | `vllm` | [vllm-project/vllm](https://github.com/vllm-project/vllm) | Apache-2.0 | external-runtime | GPU 高吞吐 OpenAI-compatible serving |
| P1 | `deepeval` | [confident-ai/deepeval](https://github.com/confident-ai/deepeval) | Apache-2.0 | adapter | LLM 回归/自定义 rubric 测试 |
| P2 | `ragas` | [vibrantlabsai/ragas](https://github.com/vibrantlabsai/ragas) | Apache-2.0 | adapter | Recall/RAG 质量指标 |
| P1 | `promptfoo` | [promptfoo/promptfoo](https://github.com/promptfoo/promptfoo) | MIT | external-tool | 模型×Prompt 矩阵与回归测试 |
| P2 | `langfuse` | [langfuse/langfuse](https://github.com/langfuse/langfuse) | MIT-core | adapter | Prompt trace、成本、延迟、实验记录；EE 目录不纳入 |
| P1 | `story_eval_dataset` | [lars76/story-evaluation-llm](https://github.com/lars76/story-evaluation-llm) | MIT | research-port | 创意写作评价维度/数据集结构参考 |
| P3 | `storybench` | [Nazuna-io/storybench](https://github.com/Nazuna-io/storybench) | NO_LICENSE_DETECTED | architecture-reference-only | 并行创作评测架构；不复制代码 |
| P2 | `ai_novel_assistant` | [sf621128/AI-Novel-Writing-Assistant](https://github.com/sf621128/AI-Novel-Writing-Assistant) | NO_LICENSE_DETECTED | architecture-reference-only | Creative Hub/RAG/小说生产链路参考；不复制代码 |
| P2 | `dspy` | [stanfordnlp/dspy](https://github.com/stanfordnlp/dspy) | MIT | experiment-candidate | 用冻结 benchmark 优化 prompt/program，而非凭感觉调 Prompt |
| P2 | `openai_evals` | [openai/evals](https://github.com/openai/evals) | MIT | research-port | 可复现实验 registry 与 eval 结构 |
| P3 | `sillytavern` | [SillyTavern/SillyTavern](https://github.com/SillyTavern/SillyTavern) | AGPL-3.0 | architecture-reference-only | Lorebook/World Info/上下文 UX 参考；不复制到 Novel |
| P3 | `koboldcpp` | [LostRuins/koboldcpp](https://github.com/LostRuins/koboldcpp) | AGPL-3.0 | external-runtime | GGUF 外部运行时，可通过 API 使用，不嵌入源码 |

## P0 integration targets

### Story generation: DOC / DOC StoryGen v2
The strongest direct architectural fit. Novel already separates plan and draft; the useful upgrade is **hierarchical outline control** and explicit premise/plan/story stages. We should port concepts, not obsolete model-serving code.

Target mapping:
- Premise candidates → Story Forge
- hierarchical outline nodes → Volume / Arc / Chapter / Scene planners
- outline expansion confidence / vagueness → choose which node to expand next
- passage generation + consistency check → current Draft/Review/Repair flow

### Reference ingestion: Docling + MarkItDown
Current `pypdf` / `python-docx` path remains the lightweight baseline. Advanced adapters should be used when layout, scanned PDFs, headers/footers or complex structure make baseline extraction unreliable.

### Chinese semantic layer: jieba + text2vec + FlagEmbedding
- jieba: deterministic lexical statistics for Style DNA.
- text2vec / BGE: semantic similarity, reference-risk checks, scene/event deduplication.
- embeddings are **not** used to imitate source wording; they are primarily an originality and recall tool.

### Local runtime: Ollama
Already compatible through Novel's OpenAI-compatible provider layer. Keep runtime external so the application does not own model binaries.

## P1 targets

### Graph memory candidates
GraphRAG, LightRAG, HippoRAG and Graphiti are deliberately **not default**. Novel's current Canon / Active / Recall memory is simple, deterministic and tested. Each graph backend must pass a frozen long-form A/B benchmark for:
- fact recall,
- character knowledge-boundary accuracy,
- foreshadowing recall,
- latency/cost,
- false-memory rate.

### Evaluation
DeepEval, promptfoo and the story-writing benchmark projects are useful for automated regression, but human blind scoring remains the authority for prose quality and "AI flavor".

### Model routing
LiteLLM can sit above Novel's existing `OpenAICompatibleProvider`; it must not replace the provider-neutral contract. This lets writer/reviewer/memory roles route to different vendors or local endpoints.

## License rules

- **MIT / Apache-2.0:** normal dependency/adaptation allowed; retain required notices when source is incorporated.
- **MIT-core:** only the upstream core covered by MIT is eligible; enterprise directories remain excluded.
- **AGPL-3.0:** keep external/reference by default; do not vendor into Novel without a deliberate license review.
- **NO_LICENSE_DETECTED:** no code copying. Architecture notes only.

## Deliberately rejected pattern: repository dumping

Cloning dozens of repositories inside `third_party/` would:
- duplicate millions of lines,
- make security/updates impossible to track,
- create conflicting Python/Node/CUDA dependency trees,
- hide which upstream actually improves novel quality,
- introduce licensing uncertainty.

The registry + adapter model gives Novel access to the same capabilities while keeping one coherent codebase.

## Next integration wave

1. Add advanced `DoclingReader` / `MarkItDownReader` adapters with deterministic fallback to current readers.
2. Add Story DNA schema/extractor using chapter boundaries + semantic event summaries.
3. Add originality gate combining shingle overlap + fuzzy + embedding + event-sequence similarity.
4. Port DOC-style hierarchical outline expansion behind an experiment flag.
5. Add Qdrant/LightRAG/HippoRAG recall adapters behind the existing `ContextAssembler`.
6. Add promptfoo/DeepEval configs for frozen chapter tests.
7. Add Fanqie-specific opening/first-20-chapter benchmark and real-platform feedback import.

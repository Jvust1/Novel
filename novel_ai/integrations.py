from __future__ import annotations

from dataclasses import asdict, dataclass
import importlib.util
from typing import Any


@dataclass(frozen=True)
class IntegrationSpec:
    key: str
    repository: str
    category: str
    license: str
    mode: str
    capability: str
    package: str = ""
    import_name: str = ""

    @property
    def github_url(self) -> str:
        return f"https://github.com/{self.repository}"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["github_url"] = self.github_url
        return data


# Keep this registry intentionally explicit: upstream projects are absorbed as
# capabilities, adapters, algorithms, external runtimes, or explicitly approved
# pinned submodules. Any source inclusion requires a compatible license and provenance.
INTEGRATIONS: tuple[IntegrationSpec, ...] = (
    IntegrationSpec("re3", "yangkevin2/emnlp22-re3-story-generation", "story_generation", "MIT", "research-port", "recursive reprompting and revision for long stories"),
    IntegrationSpec("doc_story", "yangkevin2/doc-story-generation", "story_generation", "MIT", "research-port", "detailed outline control for coherent long stories"),
    IntegrationSpec("doc_story_v2", "facebookresearch/doc-storygen-v2", "story_generation", "Apache-2.0", "research-port", "Premise -> Plan -> Story pipeline for modern chat/open models"),
    IntegrationSpec("chinese_novelist_skill", "PenglongHuang/chinese-novelist-skill", "story_generation", "MIT", "git-submodule+research-port", "Chinese novel planning, continuation and validation workflow"),
    IntegrationSpec("spacy", "explosion/spaCy", "nlp_pipeline", "MIT", "adapter+direct-optional", "PERSON entity extraction and character-consistency review hook", "spacy", "spacy"),
    IntegrationSpec("pycorrector", "shibing624/pycorrector", "chinese_quality", "Apache-2.0", "git-submodule", "Chinese spelling/grammar correction diagnostics"),
    IntegrationSpec("texthero", "jbesomi/texthero", "text_analysis", "MIT", "git-submodule", "text preprocessing and exploratory analysis"),
    IntegrationSpec("opencc", "BYVoid/OpenCC", "chinese_normalization", "Apache-2.0", "git-submodule", "Chinese script and lexical normalization"),
    IntegrationSpec("lexicalrichness", "LSYS/LexicalRichness", "style_quality", "MIT", "git-submodule", "lexical diversity and repetition diagnostics"),
    IntegrationSpec("textstat", "textstat/textstat", "style_quality", "MIT", "git-submodule", "readability and sentence-complexity diagnostics"),
    IntegrationSpec("proselint", "amperser/proselint", "style_quality", "BSD-3-Clause", "git-submodule", "prose lint heuristics; English-oriented, use as optional/reference layer"),
    IntegrationSpec("pkuseg", "lancopku/pkuseg-python", "chinese_nlp", "MIT", "git-submodule", "Chinese segmentation for lexical/style statistics"),
    IntegrationSpec("book_to_skill", "virgiliojr94/book-to-skill", "document_ingest", "MIT", "git-submodule", "convert user-provided books/documents into on-demand Agent Skills"),
    IntegrationSpec("booknlp", "booknlp/booknlp", "literary_nlp", "MIT", "research-port", "character, quote and narrative analysis ideas; English-centric, not default runtime"),
    IntegrationSpec("paddlenlp", "PaddlePaddle/PaddleNLP", "chinese_nlp", "Apache-2.0", "git-submodule+experiment-candidate", "Chinese UIE / segmentation / knowledge extraction candidate", "paddlenlp", "paddlenlp"),
    IntegrationSpec("kag", "OpenSPG/KAG", "story_structure", "Apache-2.0", "git-submodule+experiment-candidate", "knowledge augmented generation / story graph retrieval candidate", "openspg-kag", "kag"),
    IntegrationSpec("hanlp", "hankcs/HanLP", "chinese_nlp", "Apache-2.0", "git-submodule+direct-optional", "Chinese segmentation, tagging and NLP features", "hanlp", "hanlp"),
    IntegrationSpec("jieba", "fxsjy/jieba", "chinese_nlp", "MIT", "direct-optional", "lightweight Chinese tokenization for lexical statistics", "jieba", "jieba"),
    IntegrationSpec("text2vec", "shibing624/text2vec", "embeddings", "Apache-2.0", "git-submodule+adapter", "Chinese semantic embeddings and similarity", "text2vec", "text2vec"),
    IntegrationSpec("flagembedding", "FlagOpen/FlagEmbedding", "embeddings", "MIT", "git-submodule+adapter", "embedding/reranking backend for reference similarity and recall", "FlagEmbedding", "FlagEmbedding"),
    IntegrationSpec("sentence_transformers", "huggingface/sentence-transformers", "embeddings", "Apache-2.0", "git-submodule+adapter", "general sentence embeddings", "sentence-transformers", "sentence_transformers"),
    IntegrationSpec("rapidfuzz", "rapidfuzz/RapidFuzz", "longform_consistency", "MIT", "adapter+direct-optional", "entity alias/name drift after canonical/spaCy extraction plus fuzzy near-duplicate matching", "rapidfuzz", "rapidfuzz"),
    IntegrationSpec("docling", "docling-project/docling", "document_ingest", "MIT", "git-submodule+adapter", "high-quality PDF/DOCX/document conversion", "docling", "docling"),
    IntegrationSpec("markitdown", "microsoft/markitdown", "document_ingest", "MIT", "git-submodule+adapter", "document-to-markdown conversion", "markitdown", "markitdown"),
    IntegrationSpec("unstructured", "Unstructured-IO/unstructured", "document_ingest", "Apache-2.0", "adapter", "fallback document partitioning and metadata extraction", "unstructured", "unstructured"),
    IntegrationSpec("deepke", "zjunlp/DeepKE", "story_structure", "MIT", "git-submodule+experiment-candidate", "entity/relation/event extraction candidate for Story DNA; heavy backend remains opt-in"),
    IntegrationSpec("datasketch", "ekzhu/datasketch", "originality", "MIT", "git-submodule+adapter", "MinHash self-repetition screening across chapters", "datasketch", "datasketch"),
    IntegrationSpec("networkx", "networkx/networkx", "story_structure", "BSD-3-Clause", "git-submodule+adapter", "portable character/event/foreshadow graph construction", "networkx", "networkx"),
    IntegrationSpec("scikit_learn", "scikit-learn/scikit-learn", "longform_analytics", "BSD-3-Clause", "git-submodule+adapter", "Story DNA clustering and analytics", "scikit-learn", "sklearn"),
    IntegrationSpec("river", "online-ml/river", "longform_analytics", "BSD-3-Clause", "git-submodule+adapter", "online chapter drift detection", "river", "river"),
    IntegrationSpec("plotly", "plotly/plotly.py", "visualization", "MIT", "git-submodule+optional", "long-form analytics visualization", "plotly", "plotly"),
    IntegrationSpec("umap", "lmcinnes/umap", "longform_analytics", "BSD-3-Clause", "git-submodule+optional", "Story DNA 2D projection", "umap-learn", "umap"),
    IntegrationSpec("faiss", "facebookresearch/faiss", "memory_retrieval", "MIT", "git-submodule+adapter", "fast local vector Recall index", "faiss-cpu", "faiss"),
    IntegrationSpec("qdrant_client", "qdrant/qdrant-client", "memory_retrieval", "Apache-2.0", "git-submodule+adapter", "optional semantic Recall store behind A/B gate", "qdrant-client", "qdrant_client"),
    IntegrationSpec("graphrag", "microsoft/graphrag", "memory_retrieval", "MIT", "corpus-export+external-runtime", "GraphRAG text-corpus export from Novel story graph and chapter summaries", "graphrag", "graphrag"),
    IntegrationSpec("lightrag", "HKUDS/LightRAG", "memory_retrieval", "MIT", "git-submodule+experiment-candidate", "lightweight graph + vector retrieval", "lightrag-hku", "lightrag"),
    IntegrationSpec("hipporag", "OSU-NLP-Group/HippoRAG", "memory_retrieval", "MIT", "experiment-candidate", "associative graph retrieval for long-range memory"),
    IntegrationSpec("mem0", "mem0ai/mem0", "memory_retrieval", "Apache-2.0", "adapter+experiment-candidate", "optional RecallBackend adapter using add-only/infer-false writes and explicit A/B gating", "mem0ai", "mem0"),
    IntegrationSpec("graphiti", "getzep/graphiti", "memory_retrieval", "Apache-2.0", "git-submodule+experiment-candidate", "temporal knowledge graph memory", "graphiti-core", "graphiti_core"),
    IntegrationSpec("llama_index", "run-llama/llama_index", "memory_retrieval", "MIT", "adapter+direct-optional", "VectorStoreIndex-backed RecallBackend behind Novel recall contract", "llama-index", "llama_index"),
    IntegrationSpec("langchain", "langchain-ai/langchain", "orchestration", "MIT", "git-submodule+experiment-candidate", "retriever/tool/provider integration patterns", "langchain", "langchain"),
    IntegrationSpec("haystack", "deepset-ai/haystack", "orchestration", "Apache-2.0", "git-submodule+experiment-candidate", "pipeline and retrieval component patterns", "haystack-ai", "haystack"),
    IntegrationSpec("chroma", "chroma-core/chroma", "vector_store", "Apache-2.0", "git-submodule+experiment-candidate", "local vector store", "chromadb", "chromadb"),
    IntegrationSpec("qdrant", "qdrant/qdrant", "vector_store", "Apache-2.0", "experiment-candidate", "production vector database", "qdrant-client", "qdrant_client"),
    IntegrationSpec("litellm", "BerriAI/litellm", "model_routing", "MIT-core", "adapter+direct-optional", "Novel provider adapter with primary+fallback model routing across 100+ LLM providers", "litellm", "litellm"),
    IntegrationSpec("tiktoken", "openai/tiktoken", "context_budget", "MIT", "adapter+direct-optional", "token-aware Canon/Recall clipping with deterministic char fallback", "tiktoken", "tiktoken"),
    IntegrationSpec("ollama", "ollama/ollama", "model_runtime", "MIT", "external-runtime", "local model runtime", "ollama", "ollama"),
    IntegrationSpec("vllm", "vllm-project/vllm", "model_runtime", "Apache-2.0", "external-runtime", "high-throughput OpenAI-compatible model serving", "vllm", "vllm"),
    IntegrationSpec("sglang", "sgl-project/sglang", "model_runtime", "Apache-2.0", "external-runtime+openai-compatible", "high-throughput self-hosted inference exposed through Novel ProviderConfig", "", ""),
    IntegrationSpec("deepeval", "confident-ai/deepeval", "evaluation", "Apache-2.0", "adapter+direct-optional", "LLM regression and rubric metrics through Novel evaluation contract", "deepeval", "deepeval"),
    IntegrationSpec("ragas", "vibrantlabsai/ragas", "evaluation", "Apache-2.0", "git-submodule+adapter", "retrieval/memory quality evaluation", "ragas", "ragas"),
    IntegrationSpec("promptfoo", "promptfoo/promptfoo", "evaluation", "MIT", "external-tool+exporter", "prompt/model matrix regression testing via generated Promptfoo config"),
    IntegrationSpec("langfuse", "langfuse/langfuse", "observability", "MIT-core", "adapter+direct-optional", "record Novel regression metric scores against Langfuse traces", "langfuse", "langfuse"),
    IntegrationSpec("story_eval_dataset", "lars76/story-evaluation-llm", "evaluation", "MIT", "research-port", "creative-writing quality dimensions and comparison data"),
    IntegrationSpec("storybench", "Nazuna-io/storybench", "evaluation", "NO_LICENSE_DETECTED", "architecture-reference-only", "parallel creative-writing benchmark architecture"),
    IntegrationSpec("ai_novel_assistant", "sf621128/AI-Novel-Writing-Assistant", "product_reference", "NO_LICENSE_DETECTED", "architecture-reference-only", "creative hub, RAG and novel production workflow ideas"),
    IntegrationSpec("dspy", "stanfordnlp/dspy", "prompt_optimization", "MIT", "adapter+experiment-candidate", "optional review-hook program plus measurable prompt/program optimization", "dspy", "dspy"),
    IntegrationSpec("instructor", "567-labs/instructor", "structured_output", "MIT", "adapter+direct-optional", "validated Pydantic structured extraction for plans, reviews and memory deltas", "instructor", "instructor"),
    IntegrationSpec("langgraph", "langchain-ai/langgraph", "orchestration", "MIT", "adapter+experiment-candidate", "durable stateful editorial/review graph behind the external review-hook contract", "langgraph", "langgraph"),
    IntegrationSpec("pydantic_ai", "pydantic/pydantic-ai", "editorial_orchestration", "MIT", "adapter+experiment-candidate", "typed editorial agent behind the external review-hook contract", "pydantic-ai", "pydantic_ai"),
    IntegrationSpec("outlines", "dottxt-ai/outlines", "structured_output", "Apache-2.0", "adapter+direct-optional", "constrained Pydantic/JSON generation for local and OpenAI-compatible models", "outlines", "outlines"),
    IntegrationSpec("guidance", "guidance-ai/guidance", "structured_output", "MIT", "adapter+direct-optional", "regex/CFG/JSON-schema constrained generation behind StructuredExtractor", "guidance", "guidance"),
    IntegrationSpec("guardrails", "guardrails-ai/guardrails", "validation", "Apache-2.0", "adapter+direct-optional", "post-generation validators mapped into Novel review issues", "guardrails-ai", "guardrails"),
    IntegrationSpec("agent_framework", "microsoft/agent-framework", "editorial_orchestration", "MIT", "adapter+experiment-candidate", "production multi-agent editorial workflow successor to AutoGen", "agent-framework", "agent_framework"),
    IntegrationSpec("crewai", "crewAIInc/crewAI", "editorial_orchestration", "MIT", "adapter+experiment-candidate", "optional second-pass editorial Crew/Flow behind Novel's external review-hook contract", "crewai", "crewai"),
    IntegrationSpec("openai_evals", "openai/evals", "evaluation", "MIT", "research-port", "evaluation registry and reproducible benchmark patterns"),
    IntegrationSpec("sillytavern", "SillyTavern/SillyTavern", "context_product", "AGPL-3.0", "architecture-reference-only", "lorebook/world-info and context UX ideas"),
    IntegrationSpec("koboldcpp", "LostRuins/koboldcpp", "model_runtime", "AGPL-3.0", "external-runtime", "GGUF local runtime; keep outside Novel source tree"),
)


def list_integrations(*, category: str | None = None, mode: str | None = None) -> list[IntegrationSpec]:
    items = list(INTEGRATIONS)
    if category:
        items = [item for item in items if item.category == category]
    if mode:
        items = [item for item in items if item.mode == mode]
    return items


def probe_integrations() -> list[dict[str, Any]]:
    """Report whether optional Python integrations are importable.

    External tools and research references return installed=None because they
    are not expected to be imported into the Novel Python process.
    """
    rows: list[dict[str, Any]] = []
    for item in INTEGRATIONS:
        installed: bool | None = None
        if item.import_name:
            try:
                installed = importlib.util.find_spec(item.import_name) is not None
            except (ImportError, ModuleNotFoundError, ValueError):
                installed = False
        row = item.to_dict()
        row["installed"] = installed
        rows.append(row)
    return rows


def integration_summary() -> dict[str, int]:
    summary: dict[str, int] = {}
    for item in INTEGRATIONS:
        summary[item.mode] = summary.get(item.mode, 0) + 1
    return summary

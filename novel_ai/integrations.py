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
    IntegrationSpec("chinese_novelist_skill", "PenglongHuang/chinese-novelist-skill", "story_generation", "MIT", "research-port", "Chinese novel planning, continuation and validation workflow"),
    IntegrationSpec("lexicalrichness", "LSYS/LexicalRichness", "style_quality", "MIT", "git-submodule", "lexical diversity and repetition diagnostics"),
    IntegrationSpec("textstat", "textstat/textstat", "style_quality", "MIT", "git-submodule", "readability and sentence-complexity diagnostics"),
    IntegrationSpec("proselint", "amperser/proselint", "style_quality", "BSD-3-Clause", "git-submodule", "prose lint heuristics; English-oriented, use as optional/reference layer"),
    IntegrationSpec("pkuseg", "lancopku/pkuseg-python", "chinese_nlp", "MIT", "git-submodule", "Chinese segmentation for lexical/style statistics"),
    IntegrationSpec("book_to_skill", "virgiliojr94/book-to-skill", "document_ingest", "MIT", "git-submodule", "convert user-provided books/documents into on-demand Agent Skills"),
    IntegrationSpec("booknlp", "booknlp/booknlp", "literary_nlp", "MIT", "research-port", "character, quote and narrative analysis ideas; English-centric, not default runtime"),
    IntegrationSpec("hanlp", "hankcs/HanLP", "chinese_nlp", "Apache-2.0", "direct-optional", "Chinese segmentation, tagging and NLP features", "hanlp", "hanlp"),
    IntegrationSpec("jieba", "fxsjy/jieba", "chinese_nlp", "MIT", "direct-optional", "lightweight Chinese tokenization for lexical statistics", "jieba", "jieba"),
    IntegrationSpec("text2vec", "shibing624/text2vec", "embeddings", "Apache-2.0", "adapter", "Chinese semantic embeddings and similarity", "text2vec", "text2vec"),
    IntegrationSpec("flagembedding", "FlagOpen/FlagEmbedding", "embeddings", "MIT", "adapter", "embedding/reranking backend for reference similarity and recall", "FlagEmbedding", "FlagEmbedding"),
    IntegrationSpec("sentence_transformers", "huggingface/sentence-transformers", "embeddings", "Apache-2.0", "adapter", "general sentence embeddings", "sentence-transformers", "sentence_transformers"),
    IntegrationSpec("rapidfuzz", "rapidfuzz/RapidFuzz", "originality", "MIT", "direct-optional", "fast fuzzy matching for names, phrases and near-duplicates", "rapidfuzz", "rapidfuzz"),
    IntegrationSpec("docling", "docling-project/docling", "document_ingest", "MIT", "adapter", "high-quality PDF/DOCX/document conversion", "docling", "docling"),
    IntegrationSpec("markitdown", "microsoft/markitdown", "document_ingest", "MIT", "adapter", "document-to-markdown conversion", "markitdown", "markitdown"),
    IntegrationSpec("unstructured", "Unstructured-IO/unstructured", "document_ingest", "Apache-2.0", "adapter", "fallback document partitioning and metadata extraction", "unstructured", "unstructured"),
    IntegrationSpec("graphrag", "microsoft/graphrag", "memory_retrieval", "MIT", "experiment-candidate", "graph-based long-range recall", "graphrag", "graphrag"),
    IntegrationSpec("lightrag", "HKUDS/LightRAG", "memory_retrieval", "MIT", "experiment-candidate", "lightweight graph + vector retrieval", "lightrag-hku", "lightrag"),
    IntegrationSpec("hipporag", "OSU-NLP-Group/HippoRAG", "memory_retrieval", "MIT", "experiment-candidate", "associative graph retrieval for long-range memory"),
    IntegrationSpec("mem0", "mem0ai/mem0", "memory_retrieval", "Apache-2.0", "experiment-candidate", "memory extraction/retrieval patterns", "mem0ai", "mem0"),
    IntegrationSpec("graphiti", "getzep/graphiti", "memory_retrieval", "Apache-2.0", "experiment-candidate", "temporal knowledge graph memory", "graphiti-core", "graphiti_core"),
    IntegrationSpec("llama_index", "run-llama/llama_index", "orchestration", "MIT", "experiment-candidate", "index/retrieval abstractions", "llama-index", "llama_index"),
    IntegrationSpec("langchain", "langchain-ai/langchain", "orchestration", "MIT", "experiment-candidate", "retriever/tool/provider integration patterns", "langchain", "langchain"),
    IntegrationSpec("haystack", "deepset-ai/haystack", "orchestration", "Apache-2.0", "experiment-candidate", "pipeline and retrieval component patterns", "haystack-ai", "haystack"),
    IntegrationSpec("chroma", "chroma-core/chroma", "vector_store", "Apache-2.0", "experiment-candidate", "local vector store", "chromadb", "chromadb"),
    IntegrationSpec("qdrant", "qdrant/qdrant", "vector_store", "Apache-2.0", "experiment-candidate", "production vector database", "qdrant-client", "qdrant_client"),
    IntegrationSpec("litellm", "BerriAI/litellm", "model_routing", "MIT-core", "adapter", "multi-provider routing and OpenAI-compatible normalization", "litellm", "litellm"),
    IntegrationSpec("ollama", "ollama/ollama", "model_runtime", "MIT", "external-runtime", "local model runtime", "ollama", "ollama"),
    IntegrationSpec("vllm", "vllm-project/vllm", "model_runtime", "Apache-2.0", "external-runtime", "high-throughput OpenAI-compatible model serving", "vllm", "vllm"),
    IntegrationSpec("deepeval", "confident-ai/deepeval", "evaluation", "Apache-2.0", "adapter", "LLM regression and rubric evaluation", "deepeval", "deepeval"),
    IntegrationSpec("ragas", "vibrantlabsai/ragas", "evaluation", "Apache-2.0", "adapter", "retrieval/memory quality evaluation", "ragas", "ragas"),
    IntegrationSpec("promptfoo", "promptfoo/promptfoo", "evaluation", "MIT", "external-tool", "prompt/model matrix regression testing"),
    IntegrationSpec("langfuse", "langfuse/langfuse", "observability", "MIT-core", "adapter", "prompt traces, cost, latency and experiment observability", "langfuse", "langfuse"),
    IntegrationSpec("story_eval_dataset", "lars76/story-evaluation-llm", "evaluation", "MIT", "research-port", "creative-writing quality dimensions and comparison data"),
    IntegrationSpec("storybench", "Nazuna-io/storybench", "evaluation", "NO_LICENSE_DETECTED", "architecture-reference-only", "parallel creative-writing benchmark architecture"),
    IntegrationSpec("ai_novel_assistant", "sf621128/AI-Novel-Writing-Assistant", "product_reference", "NO_LICENSE_DETECTED", "architecture-reference-only", "creative hub, RAG and novel production workflow ideas"),
    IntegrationSpec("dspy", "stanfordnlp/dspy", "prompt_optimization", "MIT", "experiment-candidate", "measurable prompt/program optimization", "dspy", "dspy"),
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

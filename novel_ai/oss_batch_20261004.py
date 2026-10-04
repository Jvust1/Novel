"""Validated 20-project OSS registry for Novel (2026-10-04).

Only metadata and thin capability routing live here; upstream source trees are not copied.
"""
from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec

@dataclass(frozen=True)
class OSSProject:
    key: str
    repository: str
    stars: int
    license: str
    capability: str
    mode: str
    module: str

PROJECTS: tuple[OSSProject, ...] = (
    OSSProject("langchain", "langchain-ai/langchain", 147437, "MIT", "链式编排与工具调用", "adapter", "langchain"),
    OSSProject("llama_index", "run-llama/llama_index", 52408, "MIT", "文档索引与检索编排", "adapter", "llama_index"),
    OSSProject("haystack", "deepset-ai/haystack", 26650, "Apache-2.0", "可解释 RAG pipeline", "adapter", "haystack"),
    OSSProject("transformers", "huggingface/transformers", 166951, "Apache-2.0", "本地模型与生成", "external-runtime", "transformers"),
    OSSProject("vllm", "vllm-project/vllm", 93170, "Apache-2.0", "高吞吐推理服务", "external-runtime", "vllm"),
    OSSProject("openai_python", "openai/openai-python", 31744, "Apache-2.0", "OpenAI-compatible provider", "adapter", "openai"),
    OSSProject("pydantic", "pydantic/pydantic", 28939, "MIT", "结构化状态与响应校验", "adapter", "pydantic"),
    OSSProject("spacy", "explosion/spaCy", 33937, "MIT", "实体与句法分析", "optional-adapter", "spacy"),
    OSSProject("flag_embedding", "FlagOpen/FlagEmbedding", 12212, "MIT", "向量与重排", "optional-adapter", "FlagEmbedding"),
    OSSProject("sentence_transformers", "huggingface/sentence-transformers", 19150, "Apache-2.0", "本地 embedding 回退", "optional-adapter", "sentence_transformers"),
    OSSProject("qdrant", "qdrant/qdrant", 34930, "Apache-2.0", "向量检索后端", "external-runtime", "qdrant_client"),
    OSSProject("chroma", "chroma-core/chroma", 29437, "Apache-2.0", "轻量本地向量库", "external-runtime", "chromadb"),
    OSSProject("milvus", "milvus-io/milvus", 46317, "Apache-2.0", "规模化向量库", "external-runtime", "pymilvus"),
    OSSProject("tiktoken", "openai/tiktoken", 19380, "MIT", "上下文预算与 token 计数", "optional-adapter", "tiktoken"),
    OSSProject("jieba", "fxsjy/jieba", 35176, "MIT", "中文分词", "optional-adapter", "jieba"),
    OSSProject("rapidfuzz", "rapidfuzz/RapidFuzz", 4149, "MIT", "实体近似匹配", "optional-adapter", "rapidfuzz"),
    OSSProject("opencc", "BYVoid/OpenCC", 10027, "Apache-2.0", "中文繁简规范化", "optional-adapter", "opencc"),
    OSSProject("pycorrector", "shibing624/pycorrector", 6529, "Apache-2.0", "错别字与语病提示", "optional-adapter", "pycorrector"),
    OSSProject("trafilatura", "adbar/trafilatura", 6909, "Apache-2.0", "网页正文抽取", "optional-adapter", "trafilatura"),
    OSSProject("docling", "docling-project/docling", 68374, "MIT", "PDF/DOCX 结构化导入", "optional-adapter", "docling"),
)

PERMISSIVE_LICENSES = frozenset(["MIT","Apache-2.0","BSD-2-Clause","BSD-3-Clause","ISC","MPL-2.0"])

def list_projects(*, safe_only: bool = False, mode: str | None = None) -> list[OSSProject]:
    """Return the immutable 20-project snapshot with optional policy filters."""
    items = list(PROJECTS)
    if safe_only:
        items = [item for item in items if item.license in PERMISSIVE_LICENSES]
    if mode is not None:
        items = [item for item in items if item.mode == mode]
    return items

def available_projects(*, safe_only: bool = False) -> list[OSSProject]:
    """Return projects whose declared optional module is installed."""
    return [item for item in list_projects(safe_only=safe_only) if find_spec(item.module) is not None]

def adoption_plan() -> dict[str, list[str]]:
    """Group projects by adoption mode for review and rollback."""
    plan: dict[str, list[str]] = {}
    for item in PROJECTS:
        plan.setdefault(item.mode, []).append(item.key)
    return plan

__all__ = ["OSSProject", "PROJECTS", "PERMISSIVE_LICENSES", "list_projects", "available_projects", "adoption_plan"]

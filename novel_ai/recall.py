from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Iterable, Protocol, Sequence

from .semantic import char_ngram_similarity


@dataclass(frozen=True)
class RecallDocument:
    """A project-memory item available to an experimental recall backend."""

    document_id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RecallHit:
    document_id: str
    score: float
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


class RecallBackend(Protocol):
    name: str

    def upsert(self, documents: Iterable[RecallDocument]) -> None: ...

    def query(self, text: str, *, limit: int = 5) -> list[RecallHit]: ...


def _tokens(text: str) -> set[str]:
    compact = re.sub(r"\s+", "", text or "")
    if len(compact) <= 2:
        return {compact} if compact else set()
    return {compact[index : index + 2] for index in range(len(compact) - 1)}


class InMemoryRecallBackend:
    """Dependency-free baseline used for adapter and A/B contract tests.

    It is intentionally opt-in. ContextAssembler remains the production
    default until a backend proves equal or better continuity and latency.
    """

    name = "in-memory-baseline"

    def __init__(self, documents: Iterable[RecallDocument] = ()) -> None:
        self._documents: dict[str, RecallDocument] = {}
        self.upsert(documents)

    def upsert(self, documents: Iterable[RecallDocument]) -> None:
        for document in documents:
            if not document.document_id.strip():
                raise ValueError("RecallDocument.document_id 不能为空")
            if not document.text.strip():
                raise ValueError("RecallDocument.text 不能为空")
            self._documents[document.document_id] = document

    def query(self, text: str, *, limit: int = 5) -> list[RecallHit]:
        if limit < 1:
            raise ValueError("limit 必须至少为 1")
        if not text.strip():
            return []
        query_tokens = _tokens(text)
        hits = []
        for document in self._documents.values():
            lexical = char_ngram_similarity(text, document.text)
            overlap = len(query_tokens & _tokens(document.text)) / max(len(query_tokens), 1)
            score = round(0.7 * lexical + 0.3 * overlap, 6)
            if score > 0:
                hits.append(
                    RecallHit(
                        document_id=document.document_id,
                        score=score,
                        text=document.text,
                        metadata=document.metadata.copy(),
                    )
                )
        hits.sort(key=lambda hit: (-hit.score, hit.document_id))
        return hits[:limit]


@dataclass(frozen=True)
class RecallAdapterSpec:
    """Describes an optional backend without importing or starting it."""

    name: str
    package: str
    mode: str
    default_enabled: bool = False
    notes: str = ""


OPTIONAL_RECALL_ADAPTERS: tuple[RecallAdapterSpec, ...] = (
    RecallAdapterSpec(
        name="qdrant",
        package="qdrant-client",
        mode="vector",
        notes="需单独评测召回质量、延迟和持久化边界。",
    ),
    RecallAdapterSpec(
        name="lightrag",
        package="lightrag-hku",
        mode="graph-vector",
        notes="需验证图谱构建成本、实体漂移和知识边界。",
    ),
    RecallAdapterSpec(
        name="graphiti",
        package="graphiti-core",
        mode="temporal-graph",
        notes="需验证时间关系、事件更新和上下文可解释性。",
    ),
)


def list_recall_adapters() -> list[dict[str, Any]]:
    return [
        {
            "name": spec.name,
            "package": spec.package,
            "mode": spec.mode,
            "default_enabled": spec.default_enabled,
            "notes": spec.notes,
        }
        for spec in OPTIONAL_RECALL_ADAPTERS
    ]


def recall_preview(
    backend: RecallBackend,
    query: str,
    *,
    limit: int = 5,
) -> dict[str, Any]:
    """Return a derived preview for A/B inspection; backend text is returned only for review."""
    hits = backend.query(query, limit=limit)
    return {
        "backend": getattr(backend, "name", backend.__class__.__name__),
        "query_chars": len(query),
        "hit_count": len(hits),
        "hits": [
            {
                "document_id": hit.document_id,
                "score": hit.score,
                "metadata": hit.metadata,
                "text": hit.text,
            }
            for hit in hits
        ],
    }

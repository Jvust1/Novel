"""Optional LlamaIndex recall backend for Novel.

Upstream: run-llama/llama_index @
7e2c60a78ec27e8d146dfdd596778aea83c041d5 (MIT).
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from .recall import RecallDocument, RecallHit


class LlamaIndexRecallBackend:
    """Implement Novel's RecallBackend contract through a LlamaIndex retriever."""

    name = "llama-index"

    def __init__(self, *, index_factory: Any, document_factory: Any) -> None:
        if not callable(index_factory):
            raise TypeError("index_factory must be callable")
        if not callable(document_factory):
            raise TypeError("document_factory must be callable")
        self._index_factory = index_factory
        self._document_factory = document_factory
        self._documents: dict[str, RecallDocument] = {}
        self._index = None

    def upsert(self, documents: Iterable[RecallDocument]) -> None:
        for document in documents:
            if not isinstance(document, RecallDocument):
                raise TypeError("documents must contain RecallDocument")
            if not document.document_id.strip():
                raise ValueError("RecallDocument.document_id cannot be empty")
            if not document.text.strip():
                raise ValueError("RecallDocument.text cannot be empty")
            self._documents[document.document_id] = document
        self._rebuild()

    def _rebuild(self) -> None:
        if not self._documents:
            self._index = None
            return
        rows = [
            self._document_factory(
                text=document.text,
                doc_id=document.document_id,
                metadata=dict(document.metadata),
            )
            for document in self._documents.values()
        ]
        self._index = self._index_factory(rows)

    def query(self, text: str, *, limit: int = 5) -> list[RecallHit]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        query = str(text).strip()
        if not query or self._index is None:
            return []
        retriever = self._index.as_retriever(similarity_top_k=limit)
        rows = retriever.retrieve(query)
        hits: list[RecallHit] = []
        for index, item in enumerate(rows):
            node = getattr(item, "node", item)
            score = getattr(item, "score", 0.0)
            node_id = (
                getattr(node, "node_id", None)
                or getattr(node, "id_", None)
                or getattr(node, "ref_doc_id", None)
                or f"llama:{index}"
            )
            get_content = getattr(node, "get_content", None)
            if callable(get_content):
                content = str(get_content())
            else:
                content = str(getattr(node, "text", "") or "")
            metadata = getattr(node, "metadata", {})
            metadata = dict(metadata) if isinstance(metadata, Mapping) else {}
            if not content.strip():
                continue
            try:
                numeric_score = float(score or 0.0)
            except (TypeError, ValueError):
                numeric_score = 0.0
            hits.append(
                RecallHit(
                    document_id=str(node_id),
                    score=numeric_score,
                    text=content,
                    metadata=metadata,
                )
            )
        hits.sort(key=lambda hit: (-hit.score, hit.document_id))
        return hits[:limit]


def create_llamaindex_recall_backend() -> LlamaIndexRecallBackend:
    """Create a default in-memory LlamaIndex VectorStoreIndex lazily."""
    try:
        from llama_index.core import Document, VectorStoreIndex
    except ImportError as exc:
        raise RuntimeError(
            "LlamaIndex is optional; install requirements-extras/memory.txt before enabling it"
        ) from exc

    def index_factory(documents):
        return VectorStoreIndex.from_documents(documents)

    return LlamaIndexRecallBackend(
        index_factory=index_factory,
        document_factory=Document,
    )

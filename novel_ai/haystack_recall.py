"""Optional Haystack RecallBackend for Novel.

Upstream: deepset-ai/haystack @
0499239e66f515feab503a2768ba785cace6de91 (Apache-2.0).
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from .recall import RecallDocument, RecallHit


class HaystackRecallBackend:
    name = "haystack"

    def __init__(
        self,
        *,
        document_store: Any,
        retriever: Any,
        document_factory: Any,
    ) -> None:
        if not callable(getattr(document_store, "write_documents", None)):
            raise TypeError("document_store must provide write_documents()")
        if not callable(getattr(retriever, "run", None)):
            raise TypeError("retriever must provide run()")
        if not callable(document_factory):
            raise TypeError("document_factory must be callable")
        self._store = document_store
        self._retriever = retriever
        self._document_factory = document_factory

    def upsert(self, documents: Iterable[RecallDocument]) -> None:
        rows = []
        for document in documents:
            if not isinstance(document, RecallDocument):
                raise TypeError("documents must contain RecallDocument")
            if not document.document_id.strip() or not document.text.strip():
                raise ValueError("document_id and text cannot be empty")
            rows.append(
                self._document_factory(
                    id=document.document_id,
                    content=document.text,
                    meta=dict(document.metadata),
                )
            )
        if rows:
            try:
                self._store.write_documents(rows, policy="OVERWRITE")
            except TypeError:
                self._store.write_documents(rows)

    def query(self, text: str, *, limit: int = 5) -> list[RecallHit]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        query = str(text).strip()
        if not query:
            return []
        try:
            result = self._retriever.run(query=query, top_k=limit)
        except TypeError:
            result = self._retriever.run(query=query)
        if not isinstance(result, Mapping):
            raise RuntimeError("Haystack retriever must return a mapping")
        documents = result.get("documents", [])
        hits: list[RecallHit] = []
        for item in documents[:limit]:
            document_id = str(getattr(item, "id", "") or "").strip()
            content = str(getattr(item, "content", "") or "").strip()
            if not document_id or not content:
                continue
            raw_meta = getattr(item, "meta", {}) or {}
            metadata = dict(raw_meta) if isinstance(raw_meta, Mapping) else {}
            score = getattr(item, "score", 0.0)
            try:
                numeric_score = float(score or 0.0)
            except (TypeError, ValueError):
                numeric_score = 0.0
            hits.append(
                RecallHit(
                    document_id=document_id,
                    score=numeric_score,
                    text=content,
                    metadata=metadata,
                )
            )
        return hits


def create_haystack_recall_backend() -> HaystackRecallBackend:
    try:
        from haystack import Document
        from haystack.document_stores.in_memory import InMemoryDocumentStore
        from haystack.components.retrievers.in_memory import InMemoryBM25Retriever
    except ImportError as exc:
        raise RuntimeError(
            "Haystack is optional; install haystack-ai before enabling this recall backend"
        ) from exc

    store = InMemoryDocumentStore()
    retriever = InMemoryBM25Retriever(document_store=store)
    return HaystackRecallBackend(
        document_store=store,
        retriever=retriever,
        document_factory=Document,
    )

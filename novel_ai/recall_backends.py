from __future__ import annotations

import importlib.util
from typing import Iterable, Sequence

from .recall import RecallDocument, RecallHit
from .semantic import Encoder, vector_cosine


class LocalSemanticRecall:
    """Local semantic recall implementing the shared RecallBackend contract.

    Existing add()/search() callers remain supported, while upsert()/query()
    allow the same upper-layer code to switch between this backend and Qdrant.
    """

    name = "local-semantic"

    def __init__(self, encoder: Encoder):
        self.encoder = encoder
        self.ids: list[str] = []
        self.texts: list[str] = []
        self.metadata: list[dict] = []
        self.vectors: list[list[float]] = []
        self._faiss = None
        self._index = None

    def _encode(self, texts: Sequence[str]) -> list[list[float]]:
        rows = [list(map(float, row)) for row in self.encoder.encode(list(texts))]
        if len(rows) != len(texts):
            raise ValueError("embedding 数量与 texts 数量必须一致")
        if rows and self.vectors and len(rows[0]) != len(self.vectors[0]):
            raise ValueError("embedding 维度发生变化")
        return rows

    def _replace_all(self, docs: Sequence[RecallDocument]) -> None:
        self.ids = [str(d.document_id) for d in docs]
        self.texts = [str(d.text) for d in docs]
        self.metadata = [dict(d.metadata) for d in docs]
        self.vectors = self._encode(self.texts) if self.texts else []
        self._rebuild()

    def add(
        self,
        ids: Sequence[str],
        texts: Sequence[str],
        metadata: Sequence[dict] | None = None,
    ) -> None:
        if len(ids) != len(texts):
            raise ValueError("ids 与 texts 数量必须一致")
        if metadata is not None and len(metadata) != len(ids):
            raise ValueError("metadata 与 ids 数量必须一致")
        rows = [
            RecallDocument(str(item_id), str(text), dict((metadata or [{}] * len(ids))[i]))
            for i, (item_id, text) in enumerate(zip(ids, texts))
        ]
        self.upsert(rows)

    def upsert(self, documents: Iterable[RecallDocument]) -> None:
        incoming = list(documents)
        if not incoming:
            return
        merged = {
            item_id: RecallDocument(item_id, text, meta)
            for item_id, text, meta in zip(self.ids, self.texts, self.metadata)
        }
        for document in incoming:
            if not isinstance(document, RecallDocument):
                raise TypeError("documents 必须包含 RecallDocument")
            if not document.document_id.strip():
                raise ValueError("RecallDocument.document_id 不能为空")
            if not document.text.strip():
                raise ValueError("RecallDocument.text 不能为空")
            merged[document.document_id] = document
        self._replace_all(list(merged.values()))

    def _rebuild(self) -> None:
        self._faiss = None
        self._index = None
        if not self.vectors or importlib.util.find_spec("faiss") is None:
            return
        try:
            import faiss
            import numpy as np

            matrix = np.asarray(self.vectors, dtype="float32")
            faiss.normalize_L2(matrix)
            index = faiss.IndexFlatIP(matrix.shape[1])
            index.add(matrix)
            self._faiss = faiss
            self._index = index
        except Exception:
            self._faiss = None
            self._index = None

    def search(self, query: str, k: int = 5) -> list[RecallHit]:
        if not self.vectors or not str(query).strip():
            return []
        k = max(1, min(int(k), len(self.ids)))
        q = list(map(float, self.encoder.encode([query])[0]))
        if len(q) != len(self.vectors[0]):
            raise ValueError("query embedding 维度与索引不一致")

        if self._index is not None:
            import numpy as np

            matrix = np.asarray([q], dtype="float32")
            self._faiss.normalize_L2(matrix)
            scores, idxs = self._index.search(matrix, k)
            return [
                RecallHit(
                    document_id=self.ids[i],
                    score=round(float(score), 6),
                    text=self.texts[i],
                    metadata=dict(self.metadata[i]),
                )
                for score, i in zip(scores[0], idxs[0])
                if i >= 0
            ]

        rows = [
            RecallHit(
                document_id=self.ids[i],
                score=vector_cosine(q, vector),
                text=self.texts[i],
                metadata=dict(self.metadata[i]),
            )
            for i, vector in enumerate(self.vectors)
        ]
        return sorted(rows, key=lambda x: (-x.score, x.document_id))[:k]

    def query(self, text: str, *, limit: int = 5) -> list[RecallHit]:
        if limit < 1:
            raise ValueError("limit 必须至少为 1")
        return self.search(text, limit)


def recall_backend_capabilities() -> dict[str, bool]:
    modules = {
        "faiss": "faiss",
        "qdrant": "qdrant_client",
        "graphrag": "graphrag",
        "lightrag": "lightrag",
        "graphiti": "graphiti_core",
    }
    return {key: importlib.util.find_spec(module) is not None for key, module in modules.items()}

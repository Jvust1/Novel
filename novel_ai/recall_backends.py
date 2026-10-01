from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import importlib.util
from numbers import Integral
from threading import RLock
from typing import Iterable, Sequence

from .recall import RecallDocument, RecallHit
from .qdrant_recall import _json_safe_metadata
from .semantic import Encoder, _normalize_vector, _ordered_values, _unit_cosine, _validated_vectors


@dataclass(frozen=True)
class _RecallSnapshot:
    documents: tuple[RecallDocument, ...] = ()
    vectors: tuple[tuple[float, ...], ...] = ()
    unit_vectors: tuple[tuple[float, ...], ...] = ()
    faiss: object | None = None
    index: object | None = None


class LocalSemanticRecall:
    """Local recall with atomic, detached corpus/vector/index snapshots.

    Legacy add()/search() and read-only copies of ids/texts/metadata/vectors
    remain available. Invalid updates and optional accelerator failures leave
    the previous snapshot intact. Zero vectors are valid and score zero.
    """

    name = "local-semantic"

    def __init__(self, encoder: Encoder):
        if not callable(getattr(encoder, "encode", None)):
            raise TypeError("encoder 必须提供 encode()")
        self.encoder = encoder
        self._state = _RecallSnapshot()
        self._update_lock = RLock()
        self._updating = False

    @property
    def ids(self) -> list[str]:
        return [document.document_id for document in self._state.documents]

    @property
    def texts(self) -> list[str]:
        return [document.text for document in self._state.documents]

    @property
    def metadata(self) -> list[dict]:
        return [deepcopy(document.metadata) for document in self._state.documents]

    @property
    def vectors(self) -> list[list[float]]:
        return [list(vector) for vector in self._state.vectors]

    @property
    def _index(self):
        return self._state.index

    @property
    def _faiss(self):
        return self._state.faiss

    def _encode(self, texts: Sequence[str], *, dimension: int | None = None) -> list[list[float]]:
        try:
            values = self.encoder.encode(list(texts))
            return _validated_vectors(values, count=len(texts), dimension=dimension)
        except Exception as exc:
            raise ValueError("embedding 计算或校验失败") from exc

    @staticmethod
    def _documents(documents: Iterable[RecallDocument]) -> list[RecallDocument]:
        detached = []
        for document in documents:
            if not isinstance(document, RecallDocument):
                raise TypeError("documents 必须包含 RecallDocument")
            if not isinstance(document.document_id, str) or not document.document_id.strip():
                raise ValueError("RecallDocument.document_id 必须为非空字符串")
            if not isinstance(document.text, str) or not document.text.strip():
                raise ValueError("RecallDocument.text 必须为非空字符串")
            # Reuse the existing Qdrant adapter's safe, detached JSON contract.
            metadata = _json_safe_metadata(document.metadata)
            detached.append(RecallDocument(document.document_id, document.text, metadata))
        return detached

    def _replace_all(self, docs: Sequence[RecallDocument]) -> None:
        """Caller holds _update_lock; publish only after all work succeeds."""
        if self._updating:
            raise ValueError("encoder 或索引构建期间不能递归修改 Recall")
        self._updating = True
        try:
            state = self._state
            dimension = len(state.vectors[0]) if state.vectors else None
            vectors = self._encode([doc.text for doc in docs], dimension=dimension) if docs else []
            units = tuple(_normalize_vector(vector) for vector in vectors)
            faiss, index = self._build_index(units)
            self._state = _RecallSnapshot(
                documents=tuple(docs),
                vectors=tuple(tuple(vector) for vector in vectors),
                unit_vectors=units,
                faiss=faiss,
                index=index,
            )
        finally:
            self._updating = False

    def replace_documents(self, documents: Iterable[RecallDocument]) -> None:
        """Atomically replace the entire corpus; an empty iterable clears it.

        Duplicate IDs keep their first position and last supplied document, as
        in upsert(). Dimension remains fixed until the corpus is explicitly
        cleared. No previous/foreign documents are retained by replacement.
        """
        incoming = self._documents(documents)
        unique = {document.document_id: document for document in incoming}
        with self._update_lock:
            self._replace_all(list(unique.values()))

    def add(
        self,
        ids: Sequence[str],
        texts: Sequence[str],
        metadata: Sequence[dict] | None = None,
    ) -> None:
        if isinstance(ids, (str, bytes)) or isinstance(texts, (str, bytes)):
            raise ValueError("ids 与 texts 必须为序列，不能为单个字符串")
        if len(ids) != len(texts):
            raise ValueError("ids 与 texts 数量必须一致")
        if metadata is not None and len(metadata) != len(ids):
            raise ValueError("metadata 与 ids 数量必须一致")
        rows = [
            RecallDocument(item_id, text, metadata[i] if metadata is not None else {})
            for i, (item_id, text) in enumerate(zip(ids, texts, strict=True))
        ]
        self.upsert(rows)

    def upsert(self, documents: Iterable[RecallDocument]) -> None:
        incoming = self._documents(documents)
        if not incoming:
            return
        with self._update_lock:
            merged = {document.document_id: document for document in self._state.documents}
            for document in incoming:
                merged[document.document_id] = document
            self._replace_all(list(merged.values()))

    @staticmethod
    def _build_index(unit_vectors: Sequence[Sequence[float]]) -> tuple[object | None, object | None]:
        if not unit_vectors or importlib.util.find_spec("faiss") is None:
            return None, None
        try:
            import faiss
            import numpy as np

            # Normalize in scaled float64 math first. float32 conversion of
            # raw huge/subnormal vectors would overflow or erase direction.
            matrix = np.asarray(unit_vectors, dtype="float32")
            index = faiss.IndexFlatIP(matrix.shape[1])
            index.add(matrix)
            if index.ntotal != len(unit_vectors) or index.d != matrix.shape[1]:
                raise ValueError("FAISS 索引数量或维度与向量不一致")
            return faiss, index
        except Exception as exc:
            raise ValueError("FAISS 索引构建失败；原索引保持不变") from exc

    @staticmethod
    def _accelerated_scores(state: _RecallSnapshot, unit_query: Sequence[float]) -> dict[int, float]:
        """Check the complete accelerator result before constructing any hit.

        FlatIP is exhaustive. Fetch all rows so a top-k cutoff cannot select an
        arbitrary subset of a tie; the public order is score then document ID.
        A malformed result raises rather than silently disabling a usable index.
        """
        count = len(state.documents)
        try:
            import numpy as np

            matrix = np.asarray([unit_query], dtype="float32")
            scores, indices = state.index.search(matrix, count)
            values = _validated_vectors(scores, count=1, dimension=count)[0]
            rows = _ordered_values(indices)
            if len(rows) != 1:
                raise ValueError("FAISS 索引结果必须恰好包含一行")
            ids = _ordered_values(rows[0])
            if len(ids) != count:
                raise ValueError("FAISS 返回数量与索引不一致")
            if any(isinstance(i, bool) or not isinstance(i, Integral) for i in ids):
                raise ValueError("FAISS 索引位置必须为整数")
            if len(set(ids)) != count or any(i < 0 or i >= count for i in ids):
                raise ValueError("FAISS 返回重复或越界索引位置")
            # Float32 accumulation can overshoot a unit-vector dot slightly.
            if any(abs(score) > 1.00001 for score in values):
                raise ValueError("FAISS 相似度超出余弦范围")
            return {int(i): round(max(-1.0, min(1.0, score)), 6)
                    for i, score in zip(ids, values, strict=True)}
        except Exception as exc:
            raise ValueError("FAISS 查询失败或返回无效结果；原索引保持不变") from exc

    def search(self, query: str, k: int = 5) -> list[RecallHit]:
        if not isinstance(k, int) or isinstance(k, bool) or k < 1:
            raise ValueError("limit 必须是至少 1 的整数")
        if not isinstance(query, str):
            raise ValueError("query 必须为字符串")
        state = self._state
        if not state.documents or not query.strip():
            return []
        query_vector = self._encode([query], dimension=len(state.vectors[0]))[0]
        unit_query = _normalize_vector(query_vector)
        if state.index is not None:
            scores = self._accelerated_scores(state, unit_query)
        else:
            scores = {i: _unit_cosine(unit_query, vector)
                      for i, vector in enumerate(state.unit_vectors)}
        rows = [
            RecallHit(document_id=document.document_id, score=scores[i], text=document.text,
                      metadata=deepcopy(document.metadata))
            for i, document in enumerate(state.documents)
        ]
        return sorted(rows, key=lambda hit: (-hit.score, hit.document_id))[:k]

    def query(self, text: str, *, limit: int = 5) -> list[RecallHit]:
        return self.search(text, limit)


def recall_backend_capabilities() -> dict[str, bool]:
    modules = {
        "faiss": "faiss",
        "qdrant": "qdrant_client",
        "llama_index": "llama_index",
        "graphrag": "graphrag",
        "lightrag": "lightrag",
        "graphiti": "graphiti_core",
    }
    return {key: importlib.util.find_spec(module) is not None for key, module in modules.items()}



class _SentenceTransformerRecallEncoder:
    def __init__(self, model: object) -> None:
        encode = getattr(model, "encode", None)
        if not callable(encode):
            raise TypeError("SentenceTransformer-like model must provide encode()")
        self._model = model

    def encode(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        values = self._model.encode(
            list(texts),
            normalize_embeddings=True,
            convert_to_numpy=False,
        )
        tolist = getattr(values, "tolist", None)
        return tolist() if callable(tolist) else values


def create_sentence_transformer_recall(
    model_name_or_path: str,
    *,
    local_files_only: bool = True,
    model_factory: object | None = None,
    **model_kwargs: object,
) -> LocalSemanticRecall:
    """Create a local-first Sentence Transformers RecallBackend.

    No model download occurs by default. Tests and custom runtimes may inject a
    model_factory compatible with SentenceTransformer(...).
    """
    model_name = str(model_name_or_path).strip()
    if not model_name:
        raise ValueError("model_name_or_path cannot be empty")
    if model_factory is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers is optional; install requirements-extras/nlp.txt"
            ) from exc
        model_factory = SentenceTransformer
    if not callable(model_factory):
        raise TypeError("model_factory must be callable")
    model = model_factory(
        model_name,
        local_files_only=local_files_only,
        **model_kwargs,
    )
    backend = LocalSemanticRecall(_SentenceTransformerRecallEncoder(model))
    backend.name = "sentence-transformers-local"
    return backend

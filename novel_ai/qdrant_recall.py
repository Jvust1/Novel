"""Opt-in Qdrant adapter for Novel's recall backend contract.

Upstream API target:
- qdrant/qdrant-client v1.19.1
- commit cf747f4b6fa71ba35dfb467931f3fa65f2cdf263
- Apache-2.0
"""
from __future__ import annotations

import json
import math
import re
import uuid
from collections.abc import Callable, Iterable, Sequence
from typing import Any

from .recall import RecallDocument, RecallHit

Embedder = Callable[[Sequence[str]], Sequence[Sequence[float]]]
_COLLECTION_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_POINT_NAMESPACE = uuid.UUID("f6489cdf-92c0-5f73-83a9-281608a11646")


def _point_id(document_id: str) -> str:
    return str(uuid.uuid5(_POINT_NAMESPACE, document_id))


def _json_safe_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    try:
        encoded = json.dumps(metadata, ensure_ascii=False, allow_nan=False)
        decoded = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise ValueError("Qdrant metadata 必须可安全 JSON 序列化且不能包含 NaN/Infinity") from exc
    if not isinstance(decoded, dict):
        raise ValueError("Qdrant metadata 必须为对象")
    return decoded


class QdrantRecallBackend:
    """Qdrant implementation of Novel's existing RecallBackend protocol."""

    name = "qdrant"

    def __init__(
        self,
        *,
        client: Any,
        models_module: Any,
        embedder: Embedder,
        vector_size: int,
        collection_name: str = "novel_recall_v1",
    ) -> None:
        if not isinstance(vector_size, int) or isinstance(vector_size, bool) or vector_size < 2:
            raise ValueError("vector_size 必须是至少 2 的整数")
        if not isinstance(collection_name, str) or not _COLLECTION_RE.fullmatch(collection_name):
            raise ValueError("collection_name 只能包含字母、数字、点、下划线和连字符")
        if not callable(embedder):
            raise TypeError("embedder 必须可调用")
        self._client = client
        self._models = models_module
        self._embedder = embedder
        self._vector_size = vector_size
        self._collection_name = collection_name
        self._ensure_collection()

    @property
    def collection_name(self) -> str:
        return self._collection_name

    def _ensure_collection(self) -> None:
        if self._client.collection_exists(self._collection_name):
            return
        self._client.create_collection(
            collection_name=self._collection_name,
            vectors_config=self._models.VectorParams(
                size=self._vector_size,
                distance=self._models.Distance.COSINE,
            ),
        )

    def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        try:
            vectors = list(self._embedder(list(texts)))
        except Exception as exc:
            raise ValueError("embedding 计算失败") from exc
        if len(vectors) != len(texts):
            raise ValueError("embedding 数量与输入文本数量不一致")
        normalized: list[list[float]] = []
        for vector in vectors:
            try:
                values = [float(value) for value in vector]
            except (TypeError, ValueError) as exc:
                raise ValueError("embedding 必须是有限数值向量") from exc
            if len(values) != self._vector_size:
                raise ValueError("embedding 维度与 vector_size 不一致")
            if not all(math.isfinite(value) for value in values):
                raise ValueError("embedding 不能包含 NaN/Infinity")
            normalized.append(values)
        return normalized

    def upsert(self, documents: Iterable[RecallDocument]) -> None:
        docs = list(documents)
        if not docs:
            return
        for document in docs:
            if not isinstance(document, RecallDocument):
                raise TypeError("documents 必须包含 RecallDocument")
            if not document.document_id.strip():
                raise ValueError("RecallDocument.document_id 不能为空")
            if not document.text.strip():
                raise ValueError("RecallDocument.text 不能为空")
        vectors = self._embed([document.text for document in docs])
        points = []
        for document, vector in zip(docs, vectors, strict=True):
            payload = {
                "_novel_recall_schema": "novel-qdrant-recall-v1",
                "document_id": document.document_id,
                "text": document.text,
                "metadata": _json_safe_metadata(document.metadata),
            }
            points.append(
                self._models.PointStruct(
                    id=_point_id(document.document_id),
                    vector=vector,
                    payload=payload,
                )
            )
        self._client.upsert(collection_name=self._collection_name, points=points)

    def query(self, text: str, *, limit: int = 5) -> list[RecallHit]:
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ValueError("limit 必须至少为 1")
        if not isinstance(text, str) or not text.strip():
            return []
        query_vector = self._embed([text])[0]
        response = self._client.query_points(
            collection_name=self._collection_name,
            query=query_vector,
            limit=limit,
            with_payload=True,
        )
        hits: list[RecallHit] = []
        for point in getattr(response, "points", ()):
            payload = getattr(point, "payload", None)
            if not isinstance(payload, dict):
                raise ValueError("Qdrant 命中缺少 payload")
            if payload.get("_novel_recall_schema") != "novel-qdrant-recall-v1":
                raise ValueError("Qdrant 命中 schema 不匹配")
            document_id = payload.get("document_id")
            stored_text = payload.get("text")
            metadata = payload.get("metadata", {})
            if not isinstance(document_id, str) or not document_id:
                raise ValueError("Qdrant 命中缺少 document_id")
            if not isinstance(stored_text, str) or not stored_text:
                raise ValueError("Qdrant 命中缺少 text")
            if not isinstance(metadata, dict):
                raise ValueError("Qdrant 命中 metadata 非对象")
            score = float(getattr(point, "score", float("nan")))
            if not math.isfinite(score):
                raise ValueError("Qdrant 命中 score 非有限数")
            hits.append(
                RecallHit(
                    document_id=document_id,
                    score=score,
                    text=stored_text,
                    metadata=metadata.copy(),
                )
            )
        return hits


def create_local_qdrant_recall_backend(
    *,
    embedder: Embedder,
    vector_size: int,
    collection_name: str = "novel_recall_v1",
    location: str = ":memory:",
) -> QdrantRecallBackend:
    """Create a local-only Qdrant adapter; no remote endpoint is inferred."""
    try:
        from qdrant_client import QdrantClient, models
    except ImportError as exc:
        raise RuntimeError(
            "缺少可选依赖 qdrant-client；安装 requirements-extras/memory.txt 后再启用"
        ) from exc
    if location == ":memory:":
        client = QdrantClient(":memory:")
    else:
        if not isinstance(location, str) or not location.strip():
            raise ValueError("location 必须是本地路径或 :memory:")
        if "://" in location:
            raise ValueError("该工厂只允许本地 Qdrant；远端服务须单独显式接入")
        client = QdrantClient(path=location)
    return QdrantRecallBackend(
        client=client,
        models_module=models,
        embedder=embedder,
        vector_size=vector_size,
        collection_name=collection_name,
    )

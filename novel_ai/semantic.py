from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Set
from math import fsum, sqrt
from numbers import Real
import re
from typing import Protocol, Sequence

from pydantic import FiniteFloat, TypeAdapter, ValidationError


_FINITE_VECTOR_BATCH = TypeAdapter(list[list[FiniteFloat]])


def _ordered_values(value: object) -> list:
    """Detach ordered iterables, including NumPy arrays and encoder generators."""
    if isinstance(value, (str, bytes, bytearray, Mapping, Set)):
        raise ValueError("embedding 必须是有序数值向量")
    try:
        return list(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("embedding 必须是有序数值向量") from exc


def _validated_vectors(
    values: object, *, count: int, dimension: int | None = None,
) -> list[list[float]]:
    """Validate/detach a complete batch before its caller publishes any state.

    Pydantic supplies finite float validation. The Real guard also excludes
    NumPy bool/zero-dimensional arrays that strict float coercion would accept.
    Empty batches are allowed only for zero inputs; empty vectors are invalid.
    """
    rows = _ordered_values(values)
    if len(rows) != count:
        raise ValueError("embedding 数量与输入文本数量必须一致")
    detached = []
    for row in rows:
        cells = _ordered_values(row)
        if not cells:
            raise ValueError("embedding 向量不能为空")
        if dimension is None:
            dimension = len(cells)
        if len(cells) != dimension:
            raise ValueError("embedding 维度与索引不一致")
        if any(isinstance(cell, bool) or not isinstance(cell, Real) for cell in cells):
            raise ValueError("embedding 必须是有限实数向量，不能包含布尔值")
        detached.append(cells)
    try:
        return _FINITE_VECTOR_BATCH.validate_python(detached, strict=True)
    except ValidationError as exc:
        raise ValueError("embedding 必须是有限实数向量，不能包含 NaN/Infinity") from exc


def _normalize_vector(vector: Sequence[float]) -> tuple[float, ...]:
    """Normalize already-validated values without squaring their original scale.

    Zero vectors deliberately remain zero and have cosine similarity zero.
    Scaling first preserves huge and subnormal finite vectors, including before
    an optional accelerator converts the unit vector to float32.
    """
    scale = max(abs(value) for value in vector)
    if scale == 0:
        return tuple(0.0 for _ in vector)
    scaled = [value / scale for value in vector]
    norm = sqrt(fsum(value * value for value in scaled))
    return tuple(value / norm for value in scaled)


def _unit_cosine(a: Sequence[float], b: Sequence[float]) -> float:
    score = fsum(x * y for x, y in zip(a, b, strict=True))
    return round(max(-1.0, min(1.0, score)), 6)


class Encoder(Protocol):
    def encode(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _char_ngrams(text: str, n: int = 2) -> Counter[str]:
    compact = _compact(text)
    if not compact:
        return Counter()
    if len(compact) < n:
        return Counter({compact: 1})
    return Counter(compact[i : i + n] for i in range(len(compact) - n + 1))


def _counter_cosine(a: Counter[str], b: Counter[str]) -> float:
    if not a or not b:
        return 0.0
    common = a.keys() & b.keys()
    dot = sum(a[k] * b[k] for k in common)
    norm_a = sqrt(sum(v * v for v in a.values()))
    norm_b = sqrt(sum(v * v for v in b.values()))
    return round(dot / (norm_a * norm_b), 6) if norm_a and norm_b else 0.0


def char_ngram_similarity(text_a: str, text_b: str, *, n: int = 2) -> float:
    """Dependency-free lexical similarity fallback for Chinese prose."""
    return _counter_cosine(_char_ngrams(text_a, n), _char_ngrams(text_b, n))


def vector_cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Finite, bounded cosine; invalid/empty/mismatched vectors fail explicitly."""
    left, right = _validated_vectors([a, b], count=2)
    return _unit_cosine(_normalize_vector(left), _normalize_vector(right))


class Text2VecEncoder:
    """Lazy adapter around shibing624/text2vec."""

    def __init__(self, model_name: str = "shibing624/text2vec-base-chinese"):
        try:
            from text2vec import SentenceModel
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("需要安装 text2vec：pip install -r requirements-extras/nlp.txt") from exc
        self._model = SentenceModel(model_name)

    def encode(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return self._model.encode(list(texts))


class SentenceTransformerEncoder:
    """Lazy adapter around sentence-transformers."""

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5"):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError("需要安装 sentence-transformers：pip install -r requirements-extras/nlp.txt") from exc
        self._model = SentenceTransformer(model_name)

    def encode(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        values = self._model.encode(list(texts), normalize_embeddings=True)
        return values.tolist() if hasattr(values, "tolist") else values


class FlagEmbeddingEncoder:
    """Lazy adapter around FlagOpen/FlagEmbedding."""

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5"):
        try:
            from FlagEmbedding import FlagModel
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("需要安装 FlagEmbedding：pip install -r requirements-extras/nlp.txt") from exc
        self._model = FlagModel(model_name, use_fp16=False)

    def encode(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return self._model.encode(list(texts))


def semantic_similarity(text_a: str, text_b: str, encoder: Encoder | None = None) -> float:
    """Compare two passages.

    Without an embedding backend this intentionally falls back to character
    n-grams; callers can opt into text2vec/FlagEmbedding for semantic checks.
    """
    if encoder is None:
        return char_ngram_similarity(text_a, text_b)
    vectors = _validated_vectors(encoder.encode([text_a, text_b]), count=2)
    return _unit_cosine(_normalize_vector(vectors[0]), _normalize_vector(vectors[1]))


def max_reference_similarity(text: str, references: Sequence[str], encoder: Encoder | None = None) -> dict:
    scores = [semantic_similarity(text, ref, encoder) for ref in references]
    if not scores:
        return {"max_similarity": 0.0, "reference_index": None, "scores": []}
    best = max(range(len(scores)), key=scores.__getitem__)
    return {"max_similarity": scores[best], "reference_index": best, "scores": scores}


def preferred_encoder(prefer: str = "auto") -> tuple[Encoder | None, str]:
    """Select an installed Chinese semantic encoder without making it mandatory.

    auto preference: FlagEmbedding -> sentence-transformers -> text2vec -> dependency-free char n-grams.
    Model loading happens only when this function is explicitly called.
    """
    import importlib.util

    choice = (prefer or "auto").lower()
    if choice in {"auto", "flagembedding", "bge"} and importlib.util.find_spec("FlagEmbedding") is not None:
        try:
            return FlagEmbeddingEncoder(), "FlagEmbedding"
        except Exception:
            if choice not in {"auto"}:
                raise
    if choice in {"auto", "sentence-transformers", "sentence_transformers"} and importlib.util.find_spec("sentence_transformers") is not None:
        try:
            return SentenceTransformerEncoder(), "sentence-transformers"
        except Exception:
            if choice not in {"auto"}:
                raise
    if choice in {"auto", "text2vec"} and importlib.util.find_spec("text2vec") is not None:
        try:
            return Text2VecEncoder(), "text2vec"
        except Exception:
            if choice not in {"auto"}:
                raise
    return None, "char-ngram"

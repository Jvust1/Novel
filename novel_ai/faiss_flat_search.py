"""Flat vector search adapted from FAISS IndexFlat::search.

Source: facebookresearch/faiss, faiss/IndexFlat.cpp at commit
b0074a3fa426027d9ff8575b44386d5922859ac9. See
third_party/faiss/LICENSE and provenance.json.

The port keeps exhaustive inner-product/L2 ranking semantics with bounded,
finite Python vectors. It is used as Novel's deterministic fallback when the
optional FAISS runtime is unavailable.
"""
from __future__ import annotations

from collections.abc import Iterable
from math import fsum, isfinite
from numbers import Real
from typing import Sequence


def _rows(values: Iterable[Sequence[Real]]) -> list[list[float]]:
    rows = []
    for raw in values:
        row = list(raw)
        if not row or any(isinstance(v, bool) or not isinstance(v, Real) or not isfinite(float(v))
                           for v in row):
            raise ValueError("vectors must be non-empty finite real rows")
        rows.append([float(v) for v in row])
    if rows:
        width = len(rows[0])
        if any(len(row) != width for row in rows):
            raise ValueError("vectors must have one fixed dimension")
    return rows


def flat_search(
    query: Sequence[Real],
    vectors: Iterable[Sequence[Real]],
    *,
    k: int = 5,
    metric: str = "inner_product",
) -> list[tuple[int, float]]:
    """Exhaustively rank vectors like FAISS IndexFlat search."""
    if not isinstance(k, int) or isinstance(k, bool) or k < 1:
        raise ValueError("k must be a positive integer")
    if metric not in {"inner_product", "l2"}:
        raise ValueError("metric must be inner_product or l2")
    query_rows = _rows([query])
    rows = _rows(vectors)
    if not rows:
        return []
    if len(query_rows[0]) != len(rows[0]):
        raise ValueError("query and vectors must have the same dimension")
    scored = []
    for index, row in enumerate(rows):
        if metric == "inner_product":
            score = fsum(left * right for left, right in zip(query_rows[0], row, strict=True))
            key = (-score, index)
        else:
            score = fsum((left - right) ** 2 for left, right in zip(query_rows[0], row, strict=True))
            key = (score, index)
        scored.append((key, index, round(score, 6)))
    scored.sort(key=lambda item: item[0])
    return [(index, score) for _, index, score in scored[:k]]

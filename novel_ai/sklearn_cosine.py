"""Dependency-free cosine matrix adapted from scikit-learn.

Source: scikit-learn/sklearn/metrics/pairwise.py at commit
a442e4bb39551feb7b0af4c00075e2cb91cf9b77. See
third_party/scikit-learn/COPYING and provenance.json.

The port keeps cosine_similarity's row normalization and dot-product
semantics, with explicit finite-vector validation and bounded Python lists.
"""
from __future__ import annotations

from collections.abc import Iterable
from math import fsum, isfinite, sqrt
from numbers import Real
from typing import Sequence


def _rows(values: Iterable[Sequence[Real]]) -> list[list[float]]:
    rows: list[list[float]] = []
    for raw in values:
        row = list(raw)
        if not row:
            raise ValueError("vectors must not be empty")
        if any(isinstance(cell, bool) or not isinstance(cell, Real) or not isfinite(float(cell))
               for cell in row):
            raise ValueError("vectors must contain finite real numbers")
        rows.append([float(cell) for cell in row])
    if rows:
        dimension = len(rows[0])
        if any(len(row) != dimension for row in rows):
            raise ValueError("vectors must have the same dimension")
    return rows


def _unit(row: Sequence[float]) -> tuple[float, ...]:
    scale = max(abs(value) for value in row)
    if scale == 0:
        return tuple(0.0 for _ in row)
    scaled = [value / scale for value in row]
    norm = sqrt(fsum(value * value for value in scaled))
    return tuple(value / norm for value in scaled)


def cosine_similarity_matrix(
    X: Iterable[Sequence[Real]],
    Y: Iterable[Sequence[Real]] | None = None,
) -> list[list[float]]:
    """Return the scikit-learn-style dense cosine similarity matrix."""
    left = _rows(X)
    right = left if Y is None else _rows(Y)
    if left and right and len(left[0]) != len(right[0]):
        raise ValueError("X and Y must have the same number of features")
    normalized_left = [_unit(row) for row in left]
    normalized_right = normalized_left if Y is None else [_unit(row) for row in right]
    return [
        [round(max(-1.0, min(1.0, fsum(a * b for a, b in zip(row, other, strict=True)))), 6)
         for other in normalized_right]
        for row in normalized_left
    ]

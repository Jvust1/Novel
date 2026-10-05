"""Normalized Levenshtein similarity adapted from RapidFuzz's MIT port.

Source: rapidfuzz/RapidFuzz @ db6e504539a9c895180b266a06b36a32cb6029ee,
src/rapidfuzz/distance/Levenshtein_py.py. The normalized-distance and
normalized-similarity formulas are retained; Novel uses a bounded pure-Python
dynamic-programming implementation so the default install has no dependency.
"""

from __future__ import annotations

from collections.abc import Sequence


def levenshtein_distance(left: Sequence[object], right: Sequence[object]) -> int:
    """Return the minimum insert/delete/substitute edit count."""
    if len(left) < len(right):
        left, right = right, left
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for i, item_left in enumerate(left, start=1):
        current = [i]
        for j, item_right in enumerate(right, start=1):
            current.append(min(
                current[-1] + 1,
                previous[j] + 1,
                previous[j - 1] + (item_left != item_right),
            ))
        previous = current
    return previous[-1]


def normalized_similarity(left: object, right: object) -> float:
    """Return RapidFuzz-style similarity in the inclusive range [0, 1]."""
    if left is None or right is None:
        return 0.0
    left_seq = tuple(left)
    right_seq = tuple(right)
    maximum = max(len(left_seq), len(right_seq))
    if not maximum:
        return 1.0
    return round(1.0 - levenshtein_distance(left_seq, right_seq) / maximum, 6)

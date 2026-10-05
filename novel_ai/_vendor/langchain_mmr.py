"""LangChain's MMR selection loop, adapted to precomputed similarities.

Copyright (c) LangChain, Inc. MIT License; see third_party/langchain/LICENSE.
Source: langchain-ai/langchain @ a9780cd3dd73135d21d7130b08711685f2700d51
libs/core/langchain_core/vectorstores/utils.py:maximal_marginal_relevance

Novel adaptation: remove NumPy/model dependencies, accept a similarity callback,
and validate score inputs. Selection order and MMR equation are unchanged.
"""

from __future__ import annotations

from math import isfinite
from typing import Callable, Sequence


def maximal_marginal_relevance(
    similarity_to_query: Sequence[float],
    pair_similarity: Callable[[int, int], float],
    lambda_mult: float = 0.5,
    k: int = 4,
) -> list[int]:
    if not isfinite(lambda_mult) or not 0 <= lambda_mult <= 1:
        raise ValueError("lambda_mult must be finite and between 0 and 1")
    if any(not isfinite(score) for score in similarity_to_query):
        raise ValueError("query similarities must be finite")
    if min(k, len(similarity_to_query)) <= 0:
        return []
    most_similar = max(range(len(similarity_to_query)), key=similarity_to_query.__getitem__)
    idxs = [most_similar]
    while len(idxs) < min(k, len(similarity_to_query)):
        best_score = -float("inf")
        idx_to_add = -1
        for i, query_score in enumerate(similarity_to_query):
            if i in idxs:
                continue
            similarity_to_selected = [pair_similarity(i, j) for j in idxs]
            if any(not isfinite(score) for score in similarity_to_selected):
                raise ValueError("pair similarities must be finite")
            redundant_score = max(similarity_to_selected)
            equation_score = (
                lambda_mult * query_score - (1 - lambda_mult) * redundant_score
            )
            if equation_score > best_score:
                best_score = equation_score
                idx_to_add = i
        idxs.append(idx_to_add)
    return idxs

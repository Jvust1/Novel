"""Opt-in, local-only diverse recall of accepted chapter summaries."""

from __future__ import annotations

from functools import lru_cache
from hashlib import sha256
from heapq import nlargest
import re
from typing import Any, Sequence

from ._vendor.langchain_mmr import maximal_marginal_relevance
from .semantic import _char_ngrams, _counter_cosine


def _evidence_excerpt(query_features, text: str, max_chars: int) -> tuple[str, int, int]:
    """Keep complete sentences; never cut a negation or silently discard the match."""
    text_start = len(text) - len(text.lstrip())
    compact = text.strip()
    if len(compact) <= max_chars:
        return compact, text_start, text_start + len(compact)
    choices = []
    window = text[:2000]
    for match in re.finditer(r"[^。！？\n]+[。！？]*", window):
        # A sentence cut by the feature window is not complete evidence.
        if match.end() == len(window) and len(text) > len(window) and window[-1] not in "。！？\n":
            continue
        raw = match.group()
        sentence = raw.strip()
        start = match.start() + len(raw) - len(raw.lstrip())
        end = start + len(sentence)
        excerpt = ("…" if start > text_start else "") + sentence + ("…" if end < len(text.rstrip()) else "")
        if not sentence or len(excerpt) > max_chars:
            continue
        score = _counter_cosine(query_features, _char_ngrams(sentence))
        if score > 0:
            choices.append((score, -start, excerpt, start, end))
    if not choices:
        return "", 0, 0
    _, _, excerpt, start, end = max(choices)
    return excerpt, start, end


def select_history(
    query: str,
    summaries: Sequence[dict[str, Any]],
    *,
    limit: int = 8,
    candidate_limit: int = 64,
    lambda_mult: float = 0.5,
    summary_chars: int = 80,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Rank lexical relevance, then avoid redundant memories with LangChain MMR.

    Only caller-provided accepted summaries are read. There are no provider,
    embedding-model, database, or network calls. Canon/Active are not reranked.
    Query/summary features and the MMR pool are capped for predictable cost.
    """
    if not 1 <= limit <= candidate_limit <= 64:
        raise ValueError("require 1 <= limit <= candidate_limit <= 64")
    if summary_chars < 0:
        raise ValueError("summary_chars must not be negative")
    query_features = _char_ngrams(query[:2000])
    def relevant_rows():
        for index, row in enumerate(summaries):
            summary = str(row.get("summary", "") or "")
            excerpt, start, end = _evidence_excerpt(query_features, summary, min(summary_chars, 2000))
            if not excerpt:
                continue
            features = _char_ngrams(excerpt)
            score = _counter_cosine(query_features, features)
            if score > 0:
                yield (index, row, features, score, excerpt, start, end)

    candidates = nlargest(candidate_limit, relevant_rows(), key=lambda item: (item[3], -item[0]))

    @lru_cache(maxsize=4096)
    def pair_similarity(i: int, j: int) -> float:
        return _counter_cosine(candidates[i][2], candidates[j][2])

    indexes = maximal_marginal_relevance(
        [item[3] for item in candidates], pair_similarity, lambda_mult, limit
    )
    selected = [dict(candidates[i][1], recall_excerpt=candidates[i][4]) for i in indexes]
    report = {
        "backend": "langchain-mmr-char-bigram",
        "upstream_commit": "a9780cd3dd73135d21d7130b08711685f2700d51",
        "considered_count": len(summaries),
        "candidate_count": len(candidates),
        "lambda_mult": lambda_mult,
        "included_chapter_ids": [],
        "prompt_chars": 0,
        "selected": [
            {
                "chapter_id": str(row.get("chapter_id", "")),
                "summary_sha256": sha256(str(row.get("summary", "")).encode()).hexdigest(),
                "relevance": candidates[i][3],
                "excerpt_sha256": sha256(candidates[i][4].encode()).hexdigest(),
                "source_start": candidates[i][5],
                "source_end": candidates[i][6],
            }
            for i, row in zip(indexes, selected)
        ],
    }
    return selected, report

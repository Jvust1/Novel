"""Pure-Python PageRank adaptation for Novel story graphs.

Adapted from NetworkX's pure-Python PageRank power iteration:
networkx/networkx @ 31b74e96903d7f873b30c8ff36d71a4c9252b107,
networkx/algorithms/link_analysis/pagerank_alg.py. Novel accepts a plain
edge list and returns deterministic centrality scores without NetworkX/SciPy.
"""

from __future__ import annotations

from collections.abc import Iterable


def story_pagerank(
    nodes: Iterable[str],
    edges: Iterable[tuple[str, str, float] | tuple[str, str]],
    *,
    alpha: float = 0.85,
    max_iter: int = 100,
    tol: float = 1.0e-6,
) -> dict[str, float]:
    """Rank story nodes from incoming weighted relations."""
    node_list = list(dict.fromkeys(str(node) for node in nodes if str(node)))
    if not node_list:
        return {}
    if not 0.0 < alpha < 1.0 or max_iter < 1 or tol <= 0:
        raise ValueError("alpha, max_iter and tol must be valid positive bounds")
    outgoing: dict[str, list[tuple[str, float]]] = {node: [] for node in node_list}
    for edge in edges:
        if len(edge) not in {2, 3}:
            raise ValueError("story graph edges need source, target and optional weight")
        source, target = str(edge[0]), str(edge[1])
        if source not in outgoing or target not in outgoing:
            continue
        weight = float(edge[2]) if len(edge) == 3 else 1.0
        if weight < 0:
            raise ValueError("story graph edge weights cannot be negative")
        outgoing[source].append((target, weight))

    count = len(node_list)
    scores = {node: 1.0 / count for node in node_list}
    for _ in range(max_iter):
        previous = scores
        scores = {node: (1.0 - alpha) / count for node in node_list}
        dangling = alpha * sum(previous[node] for node in node_list if not outgoing[node])
        for node in node_list:
            scores[node] += dangling / count
        for source in node_list:
            total = sum(weight for _, weight in outgoing[source])
            if total <= 0:
                continue
            for target, weight in outgoing[source]:
                scores[target] += alpha * previous[source] * weight / total
        if sum(abs(scores[node] - previous[node]) for node in node_list) < count * tol:
            return {node: round(scores[node], 8) for node in node_list}
    raise RuntimeError("story graph PageRank did not converge")

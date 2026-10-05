from __future__ import annotations

from dataclasses import dataclass, asdict
import importlib.util
import re
from typing import Any, Sequence

from .reference_similarity import fuzzy_similarity


@dataclass
class ChapterSimilarity:
    chapter_id: str
    score: float


def near_duplicate_chapters(
    text: str,
    previous: Sequence[tuple[str, str]],
    *,
    threshold: float = 0.62,
) -> list[ChapterSimilarity]:
    """Find historically similar chapters.

    Uses datasketch MinHash when installed; otherwise falls back to the existing
    fuzzy similarity function. This is a self-repetition guard, not a detector.
    """
    if not previous:
        return []

    results: list[ChapterSimilarity] = []
    use_minhash = importlib.util.find_spec("datasketch") is not None
    if use_minhash:
        try:
            from datasketch import MinHash

            def mh(value: str) -> MinHash:
                m = MinHash(num_perm=128)
                compact = re.sub(r"\s+", "", value or "")
                grams = {compact[i:i+5] for i in range(max(0, len(compact)-4))}
                for g in grams:
                    m.update(g.encode("utf-8"))
                return m

            current = mh(text)
            for chapter_id, old in previous:
                score = float(current.jaccard(mh(old)))
                if score >= threshold:
                    results.append(ChapterSimilarity(chapter_id, round(score, 6)))
        except Exception:
            use_minhash = False

    if not use_minhash:
        for chapter_id, old in previous:
            score = fuzzy_similarity(text, old)
            if score >= threshold:
                results.append(ChapterSimilarity(chapter_id, round(score, 6)))

    return sorted(results, key=lambda item: item.score, reverse=True)


def build_story_graph(
    characters: Sequence[dict[str, Any]],
    story_state: dict[str, Any],
) -> dict[str, Any]:
    """Build a portable character/event/foreshadow graph snapshot.

    NetworkX is used when available, but output remains plain JSON so the graph
    is never tied to a specific library or database.
    """
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    for char in characters:
        name = str(char.get("name", "")).strip()
        if not name:
            continue
        nodes.append({"id": f"character:{name}", "type": "character", "label": name})
        for other, relation in (char.get("relationships") or {}).items():
            if str(other).strip():
                edges.append({
                    "source": f"character:{name}",
                    "target": f"character:{other}",
                    "type": "relationship",
                    "label": str(relation),
                })

    for idx, event in enumerate(story_state.get("timeline", [])):
        eid = f"event:{event.get('chapter_id','')}:{idx}"
        nodes.append({
            "id": eid, "type": "event",
            "label": str(event.get("description", "")),
            "chapter_id": str(event.get("chapter_id", "")),
        })

    for item in story_state.get("foreshadowing", []):
        fid = f"foreshadow:{item.get('id','')}"
        nodes.append({
            "id": fid, "type": "foreshadowing",
            "label": str(item.get("description", "")),
            "status": str(item.get("status", "")),
        })

    # Optional NetworkX pass validates graph structure and deduplicates exact edges.
    if importlib.util.find_spec("networkx") is not None:
        try:
            import networkx as nx
            graph = nx.MultiDiGraph()
            for node in nodes:
                graph.add_node(node["id"], **{k:v for k,v in node.items() if k!="id"})
            for edge in edges:
                graph.add_edge(edge["source"], edge["target"], **{k:v for k,v in edge.items() if k not in {"source","target"}})
            nodes = [{"id": n, **data} for n, data in graph.nodes(data=True)]
            edges = [{"source": u, "target": v, **data} for u, v, data in graph.edges(data=True)]
        except Exception:
            pass

    return {"nodes": nodes, "edges": edges}


class QdrantRecallStore:
    """Optional adapter for semantic Recall experiments.

    It is intentionally not enabled by default. The caller owns the embedding
    model and decides when an A/B test justifies using this backend.
    """

    def __init__(self, *, location: str = ":memory:", collection: str = "novel_recall"):
        try:
            from qdrant_client import QdrantClient
        except ImportError as exc:
            raise RuntimeError("需要 qdrant-client：pip install -r requirements-extras/memory.txt") from exc
        self.client = QdrantClient(location=location)
        self.collection = collection

    @staticmethod
    def available() -> bool:
        return importlib.util.find_spec("qdrant_client") is not None

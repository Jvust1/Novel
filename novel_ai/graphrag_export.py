"""Export Novel's story graph into a deterministic text corpus for GraphRAG.

Upstream: microsoft/graphrag @
769542fbf1d8e5b4c6a8677fefc34621c87894c5 (MIT).

GraphRAG remains an external indexing/query runtime. Novel owns canon, story
state and graph construction; this module only writes a stable corpus boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Mapping, Sequence


_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class GraphRAGDocument:
    document_id: str
    filename: str
    text: str


def _safe_name(value: str) -> str:
    cleaned = _SAFE.sub("-", value.strip()).strip("-._")
    return cleaned or "document"


class GraphRAGCorpusExporter:
    """Convert Novel story graph + chapter summaries into GraphRAG text inputs."""

    def build_documents(
        self,
        *,
        story_graph: Mapping[str, Any],
        chapter_summaries: Sequence[Mapping[str, Any]] = (),
    ) -> list[GraphRAGDocument]:
        nodes = list(story_graph.get("nodes") or [])
        edges = list(story_graph.get("edges") or [])
        docs: list[GraphRAGDocument] = []

        for node in nodes:
            if not isinstance(node, Mapping):
                continue
            node_id = str(node.get("id") or "").strip()
            if not node_id:
                continue
            label = str(node.get("label") or "").strip()
            node_type = str(node.get("type") or "entity").strip()
            lines = [
                f"# {label or node_id}",
                f"Novel node id: {node_id}",
                f"Node type: {node_type}",
            ]
            for key in sorted(node):
                if key in {"id", "label", "type"}:
                    continue
                value = node.get(key)
                if value not in (None, "", [], {}):
                    lines.append(f"{key}: {value}")
            related = [
                edge for edge in edges
                if isinstance(edge, Mapping)
                and (str(edge.get("source")) == node_id or str(edge.get("target")) == node_id)
            ]
            for edge in related:
                lines.append(
                    "Relation: "
                    f"{edge.get('source','')} -> {edge.get('target','')} "
                    f"[{edge.get('type','relationship')}] {edge.get('label','')}".strip()
                )
            docs.append(
                GraphRAGDocument(
                    document_id=node_id,
                    filename=f"node-{_safe_name(node_id)}.txt",
                    text="\n".join(lines).strip() + "\n",
                )
            )

        for row in chapter_summaries:
            if not isinstance(row, Mapping):
                continue
            chapter_id = str(row.get("chapter_id") or row.get("id") or "").strip()
            summary = str(row.get("summary") or row.get("text") or "").strip()
            if not chapter_id or not summary:
                continue
            docs.append(
                GraphRAGDocument(
                    document_id=f"chapter:{chapter_id}",
                    filename=f"chapter-{_safe_name(chapter_id)}.txt",
                    text=(
                        f"# Chapter {chapter_id}\n"
                        f"Novel chapter id: {chapter_id}\n\n"
                        f"{summary}\n"
                    ),
                )
            )

        docs.sort(key=lambda item: (item.filename, item.document_id))
        return docs

    def write_corpus(
        self,
        output_dir: str | Path,
        *,
        story_graph: Mapping[str, Any],
        chapter_summaries: Sequence[Mapping[str, Any]] = (),
    ) -> list[Path]:
        root = Path(output_dir)
        root.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for doc in self.build_documents(
            story_graph=story_graph,
            chapter_summaries=chapter_summaries,
        ):
            path = root / doc.filename
            path.write_text(doc.text, encoding="utf-8")
            written.append(path)
        return written

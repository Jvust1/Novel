from pathlib import Path
import tempfile

from novel_ai.graphrag_export import GraphRAGCorpusExporter


def graph():
    return {
        "nodes": [
            {"id": "character:林默", "type": "character", "label": "林默"},
            {"id": "event:001:0", "type": "event", "label": "接到匿名电话", "chapter_id": "001"},
        ],
        "edges": [
            {
                "source": "character:林默",
                "target": "event:001:0",
                "type": "participates",
                "label": "主角参与",
            }
        ],
    }


def test_graphrag_exporter_builds_node_and_chapter_documents():
    docs = GraphRAGCorpusExporter().build_documents(
        story_graph=graph(),
        chapter_summaries=[{"chapter_id": "001", "summary": "林默接到匿名电话。"}],
    )
    assert len(docs) == 3
    text = "\n".join(doc.text for doc in docs)
    assert "character:林默" in text
    assert "主角参与" in text
    assert "林默接到匿名电话" in text


def test_graphrag_exporter_writes_safe_text_files():
    with tempfile.TemporaryDirectory() as td:
        paths = GraphRAGCorpusExporter().write_corpus(td, story_graph=graph())
        assert paths
        assert all(path.suffix == ".txt" for path in paths)
        assert all(path.parent == Path(td) for path in paths)
        assert all(path.read_text(encoding="utf-8").strip() for path in paths)

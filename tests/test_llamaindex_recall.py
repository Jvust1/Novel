from types import SimpleNamespace

from novel_ai.llamaindex_recall import LlamaIndexRecallBackend
from novel_ai.recall import RecallDocument


class Node:
    def __init__(self, node_id, text, metadata):
        self.node_id = node_id
        self.text = text
        self.metadata = metadata

    def get_content(self):
        return self.text


class Retriever:
    def __init__(self, rows):
        self.rows = rows
    def retrieve(self, query):
        assert query == "旧案"
        return self.rows


class Index:
    def __init__(self, documents):
        self.documents = documents
    def as_retriever(self, similarity_top_k):
        assert similarity_top_k == 2
        return Retriever([
            SimpleNamespace(node=Node("a", "旧案电话", {"layer": "active"}), score=0.9),
            SimpleNamespace(node=Node("b", "雪夜商队", {"layer": "canon"}), score=0.3),
        ])


def document_factory(*, text, doc_id, metadata):
    return {"text": text, "doc_id": doc_id, "metadata": metadata}


def test_llamaindex_backend_upsert_and_query_contract():
    created = []
    def index_factory(documents):
        created.append(documents)
        return Index(documents)

    backend = LlamaIndexRecallBackend(
        index_factory=index_factory,
        document_factory=document_factory,
    )
    backend.upsert([
        RecallDocument("a", "旧案电话", {"layer": "active"}),
        RecallDocument("b", "雪夜商队", {"layer": "canon"}),
    ])
    assert len(created[0]) == 2

    hits = backend.query("旧案", limit=2)
    assert [hit.document_id for hit in hits] == ["a", "b"]
    assert hits[0].score == 0.9
    assert hits[0].metadata == {"layer": "active"}


def test_llamaindex_backend_rejects_invalid_limit():
    backend = LlamaIndexRecallBackend(
        index_factory=lambda docs: Index(docs),
        document_factory=document_factory,
    )
    try:
        backend.query("x", limit=0)
    except ValueError:
        pass
    else:
        raise AssertionError("limit=0 must fail")

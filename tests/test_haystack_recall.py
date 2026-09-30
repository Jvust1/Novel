from types import SimpleNamespace

from novel_ai.haystack_recall import HaystackRecallBackend
from novel_ai.recall import RecallDocument


class Store:
    def __init__(self):
        self.rows = []

    def write_documents(self, rows, policy=None):
        self.rows.extend(rows)


class Retriever:
    def run(self, query, top_k=None):
        assert query == "旧案"
        return {
            "documents": [
                SimpleNamespace(
                    id="a",
                    content="旧案电话",
                    meta={"layer": "active"},
                    score=0.9,
                ),
                SimpleNamespace(
                    id="b",
                    content="雪夜商队",
                    meta={"layer": "canon"},
                    score=0.2,
                ),
            ]
        }


def document_factory(**kwargs):
    return SimpleNamespace(**kwargs)


def test_haystack_backend_upsert_and_query():
    store = Store()
    backend = HaystackRecallBackend(
        document_store=store,
        retriever=Retriever(),
        document_factory=document_factory,
    )
    backend.upsert([RecallDocument("a", "旧案电话", {"layer": "active"})])
    assert store.rows[0].id == "a"
    hits = backend.query("旧案", limit=1)
    assert len(hits) == 1
    assert hits[0].document_id == "a"
    assert hits[0].metadata == {"layer": "active"}

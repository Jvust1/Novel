from novel_ai.recall import RecallDocument
from novel_ai.recall_backends import LocalSemanticRecall


class DummyEncoder:
    def encode(self, texts):
        return [[float(t.count("雨")), float(t.count("电话")), float(len(t))] for t in texts]


def test_local_semantic_recall_uses_shared_contract_and_keeps_legacy_alias():
    backend = LocalSemanticRecall(DummyEncoder())
    backend.upsert([
        RecallDocument("a", "雨一直下", {"layer": "world"}),
        RecallDocument("b", "电话响了三次", {"layer": "active"}),
    ])
    hits = backend.query("电话又响了", limit=1)
    assert hits
    assert hits[0].document_id == "b"
    assert hits[0].item_id == "b"
    assert hits[0].metadata["layer"] == "active"


def test_legacy_add_search_still_works():
    backend = LocalSemanticRecall(DummyEncoder())
    backend.add(["a"], ["电话响了"])
    assert backend.search("电话", 1)[0].item_id == "a"

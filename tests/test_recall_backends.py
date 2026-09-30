from novel_ai.recall_backends import LocalSemanticRecall, recall_backend_capabilities

class DummyEncoder:
    def encode(self,texts):
        return [[float(t.count("雨")),float(t.count("电话")),float(len(t))] for t in texts]

def test_local_semantic_recall_fallback():
    r=LocalSemanticRecall(DummyEncoder()); r.add(["a","b"],["雨一直下","电话响了三次"])
    assert r.search("电话又响了",1)

def test_capabilities_shape():
    c=recall_backend_capabilities()
    assert {"faiss","qdrant","graphrag","lightrag","graphiti"} <= set(c)

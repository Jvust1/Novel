from novel_ai.recall_backends import LocalSemanticRecall, create_sentence_transformer_recall, recall_backend_capabilities

class DummyEncoder:
    def encode(self,texts):
        return [[float(t.count("雨")),float(t.count("电话")),float(len(t))] for t in texts]

def test_local_semantic_recall_fallback():
    r=LocalSemanticRecall(DummyEncoder()); r.add(["a","b"],["雨一直下","电话响了三次"])
    assert r.search("电话又响了",1)

def test_capabilities_shape():
    c=recall_backend_capabilities()
    assert {"faiss","qdrant","graphrag","lightrag","graphiti"} <= set(c)



def test_sentence_transformer_recall_factory_is_local_first_and_preserves_docs():
    calls = []

    class Values(list):
        def tolist(self):
            return list(self)

    class Model:
        def encode(self, texts, **kwargs):
            assert kwargs["normalize_embeddings"] is True
            return Values([[float(text.count("电话")), float(len(text))] for text in texts])

    def factory(name, **kwargs):
        calls.append((name, kwargs))
        return Model()

    backend = create_sentence_transformer_recall(
        "local/model",
        model_factory=factory,
    )
    backend.add(["a", "b"], ["电话响了", "下雨了"])
    hits = backend.query("电话", limit=1)
    assert backend.name == "sentence-transformers-local"
    assert hits[0].document_id == "a"
    assert calls[0][1]["local_files_only"] is True

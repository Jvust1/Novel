from novel_ai.context import ContextAssembler
from novel_ai.recall_backends import (
    LocalSemanticRecall,
    create_native_character_recall,
    create_sentence_transformer_recall,
    recall_backend_capabilities,
)
from novel_ai.storage import ProjectStore
from unittest.mock import patch

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


def test_context_uses_registry_resolution_for_explicit_local_backend(tmp_path):
    store = ProjectStore(tmp_path)
    store.save_extraction(
        "P",
        {"chapter_id": "old", "chapter_title": "旧章", "summary": "雨落在旧桥。"},
    )
    backend = LocalSemanticRecall(DummyEncoder())
    with patch(
        "novel_ai.oss_batch_20261004.choose_recall_backend",
        return_value="native",
    ) as selector:
        context = ContextAssembler(
            store, "P", local_semantic_recall=backend,
        ).assemble(
            recent_limit=0,
            recall_query="雨",
            history_chapter_ids=["old"],
        )
    selector.assert_called_once_with()
    assert context.recall_report["registry_selected_backend"] == "native"
    assert "雨落在旧桥" in context.recall_block


def test_context_uses_configured_optional_backend_from_registry(tmp_path):
    store = ProjectStore(tmp_path)
    store.save_extraction(
        "P",
        {"chapter_id": "old", "chapter_title": "旧章", "summary": "雨落在旧桥。"},
    )
    native_backend = LocalSemanticRecall(DummyEncoder())
    native_backend.name = "native-test"
    selected_backend = LocalSemanticRecall(DummyEncoder())
    selected_backend.name = "selected-test"
    with patch(
        "novel_ai.oss_batch_20261004.choose_recall_backend",
        return_value="sentence_transformers",
    ) as selector, patch.object(
        selected_backend, "query", wraps=selected_backend.query,
    ) as query:
        context = ContextAssembler(
            store,
            "P",
            recall_backends={
                "native": native_backend,
                "sentence_transformers": selected_backend,
            },
        ).assemble(
            recent_limit=0,
            recall_query="雨",
            history_chapter_ids=["old"],
        )
    selector.assert_called_once_with()
    query.assert_called_once_with("雨", limit=8)
    assert context.recall_report["registry_selected_backend"] == "sentence_transformers"
    assert context.recall_report["backend"] == "selected-test"
    assert selected_backend.ids
    assert native_backend.ids == []


def test_context_falls_back_to_configured_native_backend(tmp_path):
    store = ProjectStore(tmp_path)
    store.save_extraction(
        "P",
        {"chapter_id": "old", "chapter_title": "旧章", "summary": "雨落在旧桥。"},
    )
    native_backend = LocalSemanticRecall(DummyEncoder())
    native_backend.name = "native-fallback-test"
    with patch(
        "novel_ai.oss_batch_20261004.choose_recall_backend",
        return_value="sentence_transformers",
    ) as selector, patch.object(
        native_backend, "query", wraps=native_backend.query,
    ) as query:
        context = ContextAssembler(
            store,
            "P",
            recall_backends={"native": native_backend},
        ).assemble(
            recent_limit=0,
            recall_query="雨",
            history_chapter_ids=["old"],
        )
    selector.assert_called_once_with()
    query.assert_called_once_with("雨", limit=8)
    assert context.recall_report["registry_selected_backend"] == "native"
    assert context.recall_report["backend"] == "native-fallback-test"
    assert native_backend.ids


def test_native_character_recall_uses_dependency_free_vectors():
    backend = create_native_character_recall()
    backend.add(["old", "other"], ["雨落在旧桥。", "电话响了。"])
    hits = backend.query("雨落在旧桥。", limit=1)
    assert backend.name == "native-character-ngram"
    assert hits[0].document_id == "old"


def test_context_uses_native_registry_path_without_selector_mock(tmp_path):
    store = ProjectStore(tmp_path)
    store.save_extraction(
        "P",
        {"chapter_id": "old", "chapter_title": "旧章", "summary": "雨落在旧桥。"},
    )
    context = ContextAssembler(
        store,
        "P",
        recall_backends={"native": create_native_character_recall()},
    ).assemble(
        recent_limit=0,
        recall_query="雨落在旧桥",
        history_chapter_ids=["old"],
    )
    assert context.recall_report["registry_selected_backend"] == "native"
    assert context.recall_report["backend"] == "native-character-ngram"
    assert context.recall_report["included_chapter_ids"] == ["old"]

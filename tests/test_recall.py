from novel_ai.recall import (
    InMemoryRecallBackend,
    RecallDocument,
    list_recall_adapters,
    recall_preview,
)


def test_in_memory_recall_is_ranked_and_metadata_safe():
    backend = InMemoryRecallBackend(
        [
            RecallDocument("a", "林默在值班室接到旧案电话。", {"layer": "active"}),
            RecallDocument("b", "市场下了一夜大雪，商队明天进城。", {"layer": "canon"}),
        ]
    )
    hits = backend.query("旧案电话", limit=2)
    assert hits[0].document_id == "a"
    assert hits[0].metadata == {"layer": "active"}
    assert hits[0].score > 0


def test_recall_backend_rejects_invalid_documents_and_limits():
    backend = InMemoryRecallBackend()
    try:
        backend.upsert([RecallDocument("", "内容")])
    except ValueError as exc:
        assert "document_id" in str(exc)
    else:
        raise AssertionError("empty document IDs must fail closed")

    backend.upsert([RecallDocument("a", "内容")])
    try:
        backend.query("内容", limit=0)
    except ValueError as exc:
        assert "limit" in str(exc)
    else:
        raise AssertionError("zero limit must fail closed")


def test_optional_adapters_are_declared_but_not_default_enabled():
    specs = list_recall_adapters()
    assert {row["name"] for row in specs} == {"mem0", "qdrant", "lightrag", "graphiti"}
    assert all(row["default_enabled"] is False for row in specs)


def test_preview_exposes_backend_identity_and_derived_counts():
    backend = InMemoryRecallBackend([RecallDocument("a", "旧案电话")])
    preview = recall_preview(backend, "旧案")
    assert preview["backend"] == "in-memory-baseline"
    assert preview["hit_count"] == 1
    assert preview["hits"][0]["document_id"] == "a"

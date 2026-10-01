"""Offline integrity checks; FAISS coverage here uses an injected test double."""
from __future__ import annotations

import math
import sys
from types import SimpleNamespace

import pytest

from novel_ai.recall import RecallDocument
from novel_ai.recall_backends import LocalSemanticRecall
from novel_ai.semantic import semantic_similarity, vector_cosine


class Encoder:
    def __init__(self):
        self.result = None
        self.error = None
        self.calls = []

    def encode(self, texts):
        self.calls.append(list(texts))
        if self.error:
            raise self.error
        if self.result is not None:
            return self.result
        return [[float("phone" in text), float("rain" in text)] for text in texts]


@pytest.fixture
def backend(monkeypatch):
    monkeypatch.setattr("novel_ai.recall_backends.importlib.util.find_spec", lambda _: None)
    encoder = Encoder()
    recall = LocalSemanticRecall(encoder)
    recall.upsert([RecallDocument("old", "phone old", {"source": {"chapters": [1]}})])
    return recall, encoder


@pytest.mark.parametrize("bad", [
    [], [[1, 0], [0, 1]], [[]], [[1]], [[1, 2, 3]],
    [[math.nan, 0]], [[math.inf, 0]], [[-math.inf, 0]],
    [[True, 0]], [["1", 0]], [None], ["10"], [[None, 0]],
    "10", {"row": [1, 0]}, [[10**400, 0]],
])
def test_failed_update_preserves_every_record_and_vector(backend, bad):
    recall, encoder = backend
    before = (recall.ids, recall.texts, recall.metadata, recall.vectors, recall._index)
    encoder.result = bad
    with pytest.raises(ValueError):
        recall.upsert([RecallDocument("old", "rain replacement", {"new": True})])
    assert (recall.ids, recall.texts, recall.metadata, recall.vectors, recall._index) == before
    encoder.result = None
    assert recall.query("phone")[0].text == "phone old"


def test_encoder_exception_does_not_publish_partial_state(backend):
    recall, encoder = backend
    encoder.error = RuntimeError("encoder failed")
    with pytest.raises(ValueError, match="embedding"):
        recall.add(["new"], ["rain"])
    encoder.error = None
    assert recall.ids == ["old"]
    assert recall.query("phone")[0].text == "phone old"


@pytest.mark.parametrize("bad", [[[1, 0], [1]], [[1, 0], []], [[1, 0], [math.nan, 0]]])
def test_ragged_or_nonfinite_second_row_is_atomic(backend, bad):
    recall, encoder = backend
    encoder.result = bad
    with pytest.raises(ValueError):
        recall.add(["new"], ["rain"])
    assert recall.ids == ["old"]


@pytest.mark.parametrize("bad", [[], [[1, 0], [0, 1]], [[]], [[1]], [[math.nan, 1]], [[True, 1]], None, "12"])
def test_query_rejects_malformed_encoder_batch(backend, bad):
    recall, encoder = backend
    original = encoder.encode
    encoder.encode = lambda texts: bad
    with pytest.raises(ValueError):
        recall.query("phone")
    encoder.encode = original
    assert recall.query("phone")[0].document_id == "old"


@pytest.mark.parametrize("bad", [True, False, 1.0, 1.5, "2", None, 0, -1])
@pytest.mark.parametrize("method", ["query", "search"])
def test_limits_are_positive_non_bool_integers_even_on_empty_index(bad, method):
    recall = LocalSemanticRecall(Encoder())
    with pytest.raises(ValueError):
        getattr(recall, method)("phone", **({"limit": bad} if method == "query" else {"k": bad}))


@pytest.mark.parametrize("bad", [None, 12, [], b"phone"])
def test_nontext_query_is_rejected(backend, bad):
    recall, encoder = backend
    before = len(encoder.calls)
    with pytest.raises(ValueError):
        recall.query(bad)
    assert len(encoder.calls) == before


def test_blank_query_and_empty_collection_do_not_call_encoder(backend):
    recall, encoder = backend
    before = len(encoder.calls)
    assert recall.query(" \n ") == []
    assert len(encoder.calls) == before
    assert LocalSemanticRecall(encoder).query("phone") == []
    assert len(encoder.calls) == before


def test_metadata_is_json_safe_and_detached_on_both_sides(backend):
    recall, encoder = backend
    metadata = {"nested": {"chapters": [2]}}
    recall.upsert([RecallDocument("old", "phone", metadata)])
    metadata["nested"]["chapters"].append(3)
    hit = recall.query("phone")[0]
    assert hit.metadata == {"nested": {"chapters": [2]}}
    hit.metadata["nested"]["chapters"].append(4)
    recall.metadata[0]["nested"]["chapters"].append(5)
    assert recall.query("phone")[0].metadata == {"nested": {"chapters": [2]}}


@pytest.mark.parametrize("bad", [[], {"bad": object()}, {"bad": math.nan}, {"bad": math.inf}])
def test_bad_metadata_does_not_call_encoder_or_publish(backend, bad):
    recall, encoder = backend
    before = len(encoder.calls)
    with pytest.raises(ValueError):
        recall.upsert([RecallDocument("old", "replacement", bad)])
    assert len(encoder.calls) == before
    assert recall.texts == ["phone old"]


def test_exposed_legacy_lists_cannot_corrupt_snapshot(backend):
    recall, _ = backend
    recall.ids[0] = "fake"
    recall.texts[0] = "fake"
    recall.vectors[0][0] = -1
    assert recall.query("phone")[0].document_id == "old"
    assert recall.query("phone")[0].score == 1.0


def test_duplicate_upserts_replace_in_place_and_keep_deterministic_ties(backend):
    recall, _ = backend
    recall.upsert([RecallDocument("z", "phone z"), RecallDocument("a", "phone a"),
                   RecallDocument("z", "phone newest")])
    assert recall.ids == ["old", "z", "a"]
    hits = recall.search("phone", 100)
    assert [hit.document_id for hit in hits] == ["a", "old", "z"]
    assert hits[-1].text == "phone newest"


@pytest.mark.parametrize("a,b,expected", [
    ([1e308, 1e308], [1e308, 1e308], 1.0),
    ([1e308, 1e308], [-1e308, -1e308], -1.0),
    ([1e308, 1e308], [1e308, -1e308], 0.0),
    ([5e-324, 5e-324], [5e-324, 5e-324], 1.0),
    ([5e-324, 0], [0, 5e-324], 0.0),
    ([0, 0], [1e308, 1e308], 0.0),
    ([0, 0], [0, 0], 0.0),
])
def test_cosine_is_overflow_and_underflow_safe(a, b, expected):
    assert vector_cosine(a, b) == expected


@pytest.mark.parametrize("a,b", [([], []), ([1], [1, 2]), ([math.nan], [1]),
                                       ([math.inf], [1]), ([True], [1]), (["1"], [1])])
def test_cosine_rejects_invalid_vectors(a, b):
    with pytest.raises(ValueError):
        vector_cosine(a, b)


def test_semantic_similarity_validates_entire_batch():
    encoder = Encoder()
    encoder.result = [[1, 2], [1]]
    with pytest.raises(ValueError):
        semantic_similarity("first", "second", encoder)
    assert math.isfinite(semantic_similarity("first", "second"))


def install_faiss_stub(monkeypatch):
    np = pytest.importorskip("numpy")
    state = SimpleNamespace(indexes=[], fail_add=False, fail_search=False, output=None, bad_count=False, bad_dimension=False)

    class IndexFlatIP:
        def __init__(self, dimension):
            self.d = dimension + int(state.bad_dimension)
            self.ntotal = 0
            state.indexes.append(self)

        def add(self, matrix):
            assert matrix.dtype == np.float32
            assert np.isfinite(matrix).all()
            assert (np.linalg.norm(matrix, axis=1) <= 1.000001).all()
            if state.fail_add:
                raise RuntimeError("synthetic add failure")
            self.matrix = matrix.copy()
            self.ntotal = len(matrix) - int(state.bad_count)

        def search(self, matrix, k):
            assert matrix.dtype == np.float32
            assert np.isfinite(matrix).all()
            assert (np.linalg.norm(matrix, axis=1) <= 1.000001).all()
            if state.fail_search:
                raise RuntimeError("synthetic search failure")
            if state.output is not None:
                return state.output
            scores = (matrix @ self.matrix.T)[0]
            # Deliberately reverse ties to check deterministic cutoff behavior.
            indices = sorted(range(len(scores)), key=lambda i: (-float(scores[i]), -i))[:k]
            return np.array([[scores[i] for i in indices]]), np.array([indices])

    monkeypatch.setitem(sys.modules, "faiss", SimpleNamespace(IndexFlatIP=IndexFlatIP))
    monkeypatch.setattr("novel_ai.recall_backends.importlib.util.find_spec", lambda _: object())
    return state


def test_faiss_normalizes_before_float32_and_keeps_tied_cutoffs_stable(monkeypatch):
    state = install_faiss_stub(monkeypatch)
    encoder = Encoder()
    recall = LocalSemanticRecall(encoder)
    encoder.result = [[1e308, 1e308], [5e-324, 5e-324], [0, 0]]
    recall.add(["z", "a", "zero"], ["huge", "tiny", "zero"])
    encoder.result = [[1e308, 1e308]]
    assert [h.document_id for h in recall.query("huge", limit=1)] == ["a"]
    encoder.result = [[5e-324, 5e-324]]
    hits = recall.query("tiny")
    assert [(h.document_id, h.score) for h in hits] == [("a", 1.0), ("z", 1.0), ("zero", 0.0)]
    assert len(state.indexes) == 1


def test_failed_faiss_build_preserves_old_usable_index(monkeypatch):
    state = install_faiss_stub(monkeypatch)
    recall = LocalSemanticRecall(Encoder())
    recall.add(["old"], ["phone"])
    old_index = recall._index
    state.fail_add = True
    with pytest.raises(ValueError):
        recall.add(["new"], ["rain"])
    assert recall._index is old_index
    assert recall.ids == ["old"]
    assert recall.query("phone")[0].text == "phone"


@pytest.mark.parametrize("output", [
    ([[math.nan]], [[0]]), ([[math.inf]], [[0]]), ([[2.0]], [[0]]),
    ([[0.5]], [[-1]]), ([[0.5]], [[1]]), ([[0.5]], [[True]]), ([[0.5]], [[0.0]]),
    ([], []), ([[0.5, 0.5]], [[0, 0]]), ([[0.5]], []),
    ([[0.5], [0.5]], [[0], [0]]), ("bad", [[0]]),
])
def test_invalid_faiss_results_fail_closed_without_mutating_index(monkeypatch, output):
    state = install_faiss_stub(monkeypatch)
    recall = LocalSemanticRecall(Encoder())
    recall.add(["old"], ["phone"])
    old_index = recall._index
    state.output = output
    with pytest.raises(ValueError):
        recall.query("phone")
    assert recall._index is old_index
    state.output = None
    assert recall.query("phone")[0].score == 1.0


def test_failed_faiss_search_preserves_index(monkeypatch):
    state = install_faiss_stub(monkeypatch)
    recall = LocalSemanticRecall(Encoder())
    recall.add(["old"], ["phone"])
    old_index = recall._index
    state.fail_search = True
    with pytest.raises(ValueError):
        recall.query("phone")
    assert recall._index is old_index
    state.fail_search = False
    assert recall.query("phone")[0].score == 1.0


def test_replace_documents_removes_foreign_corpus_and_empty_resets_dimension(backend):
    recall, encoder = backend
    recall.replace_documents([RecallDocument("new", "rain", {"project": "current"})])
    assert recall.ids == ["new"]
    assert recall.query("phone")[0].document_id == "new"
    calls = len(encoder.calls)
    recall.replace_documents([])
    assert recall.ids == recall.texts == recall.metadata == recall.vectors == []
    assert recall._index is None
    assert recall.query("phone") == []
    assert len(encoder.calls) == calls
    encoder.result = [[1, 0, 0]]
    recall.replace_documents([RecallDocument("three", "three dimensions")])
    assert recall.vectors == [[1.0, 0.0, 0.0]]


def test_replace_documents_validates_every_document_before_encode(backend):
    recall, encoder = backend
    before = len(encoder.calls)
    with pytest.raises(ValueError):
        recall.replace_documents([RecallDocument("valid", "rain"), RecallDocument("bad", " ")])
    assert len(encoder.calls) == before
    assert recall.ids == ["old"]
    encoder.result = [[math.nan, 0]]
    with pytest.raises(ValueError):
        recall.replace_documents([RecallDocument("new", "rain")])
    assert recall.ids == ["old"]


def test_replace_documents_retains_last_duplicate_only(backend):
    recall, _ = backend
    recall.replace_documents([RecallDocument("a", "rain"), RecallDocument("a", "phone")])
    assert recall.ids == ["a"]
    assert recall.query("phone")[0].text == "phone"


def test_lazy_encoder_output_is_detached(backend):
    recall, encoder = backend
    row = [0, 1]
    encoder.result = (iter(row) for _ in range(1))
    recall.replace_documents([RecallDocument("new", "rain")])
    row[1] = -1
    assert recall.vectors == [[0.0, 1.0]]


def test_numpy_numeric_arrays_are_supported_but_bool_complex_and_scalar_arrays_are_not(backend):
    np = pytest.importorskip("numpy")
    recall, encoder = backend
    encoder.result = np.array([[np.float32(1), np.int64(0)]])
    recall.replace_documents([RecallDocument("new", "phone")])
    assert recall.query("phone")[0].score == 1.0
    assert vector_cosine(np.array([1e308, 1e308]), np.array([5e-324, 5e-324])) == 1.0
    for bad in [np.bool_(True), np.array(1.2), np.complex128(2 + 1j)]:
        encoder.result = [[bad, 1]]
        with pytest.raises(ValueError):
            recall.replace_documents([RecallDocument("bad", "rain")])
        assert recall.ids == ["new"]


def test_query_uses_one_snapshot_when_encoder_updates_corpus(backend):
    recall, encoder = backend
    original = encoder.encode

    def reentrant_encode(texts):
        encoder.encode = original
        recall.replace_documents([RecallDocument("new", "rain")])
        return [[1, 0]]

    encoder.encode = reentrant_encode
    hit = recall.query("phone")[0]
    assert (hit.document_id, hit.text, hit.score) == ("old", "phone old", 1.0)
    assert recall.query("rain")[0].document_id == "new"


def test_concurrent_upserts_do_not_lose_documents(backend):
    from concurrent.futures import ThreadPoolExecutor

    recall, _ = backend
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda i: recall.upsert([RecallDocument(str(i), "phone")]), range(16)))
    assert set(recall.ids) == {"old", *(str(i) for i in range(16))}
    assert len(recall.query("phone", limit=100)) == 17


@pytest.mark.parametrize("document", [RecallDocument("", "phone"), RecallDocument(1, "phone"),
                                       RecallDocument("a", None), RecallDocument("a", " ")])
def test_invalid_document_fields_are_atomic(backend, document):
    recall, encoder = backend
    calls = len(encoder.calls)
    with pytest.raises(ValueError):
        recall.upsert([document])
    assert len(encoder.calls) == calls
    assert recall.ids == ["old"]


def test_rejects_non_document_before_encoder(backend):
    recall, encoder = backend
    calls = len(encoder.calls)
    with pytest.raises(TypeError):
        recall.upsert([{"document_id": "a", "text": "phone"}])
    assert len(encoder.calls) == calls


@pytest.mark.parametrize("ids,texts,metadata", [
    (["a"], [], None), (["a"], ["phone"], []),
    ("a", ["phone"], None), (["a"], "phone", None),
])
def test_legacy_add_rejects_invalid_batch_shape(backend, ids, texts, metadata):
    recall, encoder = backend
    calls = len(encoder.calls)
    with pytest.raises(ValueError):
        recall.add(ids, texts, metadata)
    assert len(encoder.calls) == calls
    assert recall.ids == ["old"]


def test_accelerator_small_numeric_overshoot_is_bounded(monkeypatch):
    state = install_faiss_stub(monkeypatch)
    recall = LocalSemanticRecall(Encoder())
    recall.add(["old"], ["phone"])
    state.output = ([[1.0000001]], [[0]])
    assert recall.query("phone")[0].score == 1.0


def test_no_accelerator_path_handles_extreme_and_zero_vectors(backend):
    recall, encoder = backend
    encoder.result = [[1e308, 1e308], [5e-324, 5e-324], [0, 0]]
    recall.replace_documents([RecallDocument("z", "huge"), RecallDocument("a", "tiny"),
                              RecallDocument("zero", "zero")])
    encoder.result = [[5e-324, 5e-324]]
    assert [(h.document_id, h.score) for h in recall.query("tiny")] == [
        ("a", 1.0), ("z", 1.0), ("zero", 0.0)]
    encoder.result = [[0, 0]]
    assert [(h.document_id, h.score) for h in recall.query("zero")] == [
        ("a", 0.0), ("z", 0.0), ("zero", 0.0)]


@pytest.mark.parametrize("nested_method", ["upsert", "replace_documents"])
def test_recursive_encoder_mutation_is_rejected_and_recovery_remains_usable(backend, nested_method):
    recall, encoder = backend
    original = encoder.encode

    def recursive_encode(texts):
        encoder.encode = original
        getattr(recall, nested_method)([RecallDocument("nested", "rain nested")])
        return original(texts)

    encoder.encode = recursive_encode
    with pytest.raises(ValueError):
        recall.upsert([RecallDocument("outer", "phone outer")])
    assert recall.ids == ["old"]
    assert recall.query("phone")[0].text == "phone old"
    recall.upsert([RecallDocument("later", "rain")])
    assert recall.ids == ["old", "later"]


@pytest.mark.parametrize("fault", ["bad_count", "bad_dimension"])
def test_incoherent_accelerator_build_is_not_published(monkeypatch, fault):
    state = install_faiss_stub(monkeypatch)
    recall = LocalSemanticRecall(Encoder())
    recall.add(["old"], ["phone"])
    old_index = recall._index
    setattr(state, fault, True)
    with pytest.raises(ValueError):
        recall.replace_documents([RecallDocument("new", "rain")])
    assert recall._index is old_index
    assert recall.ids == ["old"]
    assert recall.query("phone")[0].text == "phone"

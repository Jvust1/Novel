from __future__ import annotations

from types import SimpleNamespace
import unittest

from novel_ai.qdrant_recall import QdrantRecallBackend, _point_id
from novel_ai.recall import RecallDocument


class FakeModels:
    class Distance:
        COSINE = "cosine"

    class VectorParams:
        def __init__(self, *, size, distance):
            self.size = size
            self.distance = distance

    class PointStruct:
        def __init__(self, *, id, vector, payload):
            self.id = id
            self.vector = vector
            self.payload = payload


class FakeClient:
    def __init__(self):
        self.created = []
        self.points = []
        self.queries = []

    def collection_exists(self, name):
        return bool(self.created)

    def create_collection(self, **kwargs):
        self.created.append(kwargs)

    def upsert(self, *, collection_name, points):
        self.points = list(points)

    def query_points(self, **kwargs):
        self.queries.append(kwargs)
        return SimpleNamespace(
            points=[SimpleNamespace(score=0.8, payload=self.points[0].payload)]
        )


def embed(texts):
    return [[float(len(text)), 1.0, 0.5] for text in texts]


class QdrantRecallContractTests(unittest.TestCase):
    def test_round_trip_maps_recall_contract_without_raw_id_assumptions(self):
        client = FakeClient()
        backend = QdrantRecallBackend(
            client=client, models_module=FakeModels, embedder=embed, vector_size=3
        )
        backend.upsert(
            [RecallDocument("canon:1", "林默接到旧案电话", {"layer": "canon"})]
        )
        self.assertEqual(client.points[0].id, _point_id("canon:1"))
        hits = backend.query("旧案", limit=1)
        self.assertEqual(hits[0].document_id, "canon:1")
        self.assertEqual(hits[0].metadata, {"layer": "canon"})
        self.assertTrue(client.queries[-1]["with_payload"])

    def test_bad_vector_fails_before_write(self):
        client = FakeClient()
        backend = QdrantRecallBackend(
            client=client,
            models_module=FakeModels,
            embedder=lambda texts: [[1.0] for _ in texts],
            vector_size=3,
        )
        with self.assertRaisesRegex(ValueError, "维度"):
            backend.upsert([RecallDocument("a", "内容")])
        self.assertEqual(client.points, [])

    def test_non_json_metadata_fails_closed(self):
        client = FakeClient()
        backend = QdrantRecallBackend(
            client=client, models_module=FakeModels, embedder=embed, vector_size=3
        )
        with self.assertRaisesRegex(ValueError, "JSON"):
            backend.upsert([RecallDocument("a", "内容", {"bad": float("nan")})])

    def test_invalid_limits_and_collection_names_fail_closed(self):
        client = FakeClient()
        backend = QdrantRecallBackend(
            client=client, models_module=FakeModels, embedder=embed, vector_size=3
        )
        self.assertEqual(backend.query("   "), [])
        with self.assertRaises(ValueError):
            backend.query("内容", limit=0)
        with self.assertRaises(ValueError):
            QdrantRecallBackend(
                client=client,
                models_module=FakeModels,
                embedder=embed,
                vector_size=3,
                collection_name="../bad",
            )


if __name__ == "__main__":
    unittest.main()

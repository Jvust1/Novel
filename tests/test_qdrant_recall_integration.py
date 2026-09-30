from __future__ import annotations

import importlib.util
import unittest

from novel_ai.qdrant_recall import create_local_qdrant_recall_backend
from novel_ai.recall import RecallDocument


def tiny_embedder(texts):
    vectors = []
    for text in texts:
        if "旧案" in text or "电话" in text:
            vectors.append([1.0, 0.0, 0.0])
        elif "雪" in text or "商队" in text:
            vectors.append([0.0, 1.0, 0.0])
        else:
            vectors.append([0.0, 0.0, 1.0])
    return vectors


@unittest.skipUnless(
    importlib.util.find_spec("qdrant_client"),
    "qdrant-client optional dependency absent",
)
class QdrantRealClientIntegrationTests(unittest.TestCase):
    def test_in_memory_qdrant_returns_expected_canon_item(self):
        backend = create_local_qdrant_recall_backend(
            embedder=tiny_embedder,
            vector_size=3,
            collection_name="novel_recall_contract_test",
        )
        backend.upsert(
            [
                RecallDocument("canon:old-case", "林默接到旧案电话。", {"layer": "canon"}),
                RecallDocument("world:snow", "城外大雪，商队延迟。", {"layer": "world"}),
            ]
        )
        hits = backend.query("旧案", limit=1)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].document_id, "canon:old-case")
        self.assertEqual(hits[0].metadata["layer"], "canon")


if __name__ == "__main__":
    unittest.main()

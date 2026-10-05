import unittest
from unittest.mock import patch

from novel_ai.oss_batch_20261004 import (
    PROJECTS,
    adoption_plan,
    choose_backend,
    choose_recall_backend,
    list_projects,
)
from novel_ai.recall_backends import recall_backend_capabilities


class OssBatchTests(unittest.TestCase):
    def test_snapshot_has_twenty_projects(self):
        self.assertEqual(len(PROJECTS), 20)
        self.assertEqual(len(list_projects(safe_only=True)), 20)

    def test_modes_are_grouped(self):
        plan = adoption_plan()
        self.assertIn("optional-adapter", plan)
        self.assertIn("external-runtime", plan)

    def test_unknown_backend_falls_back_to_native(self):
        self.assertEqual(choose_backend(("missing_backend",)), "native")

    def test_installed_safe_recall_backend_is_selected(self):
        with patch(
            "novel_ai.oss_batch_20261004.find_spec",
            side_effect=lambda module: object() if module == "sentence_transformers" else None,
        ):
            self.assertEqual(
                choose_recall_backend(("sentence_transformers",)),
                "sentence_transformers",
            )

    def test_recall_capability_probe_calls_validated_selector(self):
        with patch(
            "novel_ai.oss_batch_20261004.choose_recall_backend",
            return_value="llama_index",
        ) as selector:
            capabilities = recall_backend_capabilities()
        selector.assert_called_once_with()
        self.assertEqual(capabilities["selected_backend"], "llama_index")


if __name__ == "__main__":
    unittest.main()

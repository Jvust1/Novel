import unittest

from novel_ai.oss_batch_20261004 import PROJECTS, adoption_plan, list_projects

class OssBatchTests(unittest.TestCase):
    def test_snapshot_has_twenty_projects(self):
        self.assertEqual(len(PROJECTS), 20)
        self.assertEqual(len(list_projects(safe_only=True)), 20)

    def test_modes_are_grouped(self):
        plan = adoption_plan()
        self.assertIn("optional-adapter", plan)
        self.assertIn("external-runtime", plan)

if __name__ == "__main__":
    unittest.main()

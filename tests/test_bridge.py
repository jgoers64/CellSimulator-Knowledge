"""Smoke the viewer-side adapter without importing a Pygame window."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from knowledge.knowledge_store import build_database
from sim import knowledge_bridge


class KnowledgeBridgeTests(unittest.TestCase):
    def setUp(self):
        knowledge_bridge.concept_by_id.cache_clear()

    def tearDown(self):
        knowledge_bridge.concept_by_id.cache_clear()

    def test_missing_local_db_does_not_block_simulator(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(knowledge_bridge, "DEFAULT_DB", Path(temp) / "missing.db"):
                self.assertIsNone(knowledge_bridge.concept_by_id("bio:dna"))
                self.assertIsNone(knowledge_bridge.concept_for_molecule("nucleotides/dna/b_dna_cg_1bna"))

    def test_existing_dna_ref_and_exact_label_query(self):
        with tempfile.TemporaryDirectory() as temp:
            target = build_database(destination=Path(temp) / "knowledge.sqlite3")
            with patch.object(knowledge_bridge, "DEFAULT_DB", target):
                dna = knowledge_bridge.concept_for_molecule("nucleotides/dna/b_dna_cg_1bna")
                self.assertEqual(dna["id"], "bio:dna")
                self.assertEqual(dna["status"], "source_checked")
                self.assertEqual(
                    knowledge_bridge.concept_for_exact_label("pyrimidine")["id"],
                    "chem:pyrimidine",
                )
                self.assertIsNone(knowledge_bridge.concept_for_exact_label("unknown thing"))


if __name__ == "__main__":
    unittest.main()

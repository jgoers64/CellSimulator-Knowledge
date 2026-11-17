"""Offline regression tests for the source of truth and SQLite knowledge index."""
from __future__ import annotations

import json
from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path

from knowledge.knowledge_store import (
    ROOT, KnowledgeError, KnowledgeStore, build_database, read_concepts, read_sources,
)


class KnowledgeTests(unittest.TestCase):
    def test_source_records_and_cross_references_are_valid(self):
        concepts = read_concepts(ROOT)
        self.assertGreaterEqual(len(concepts), 7)
        self.assertTrue(all(c["status"] == "source_checked" for c in concepts))
        self.assertTrue(all(c["sources"] for c in concepts))
        self.assertGreaterEqual(len(read_sources(ROOT)), 3)

    def test_build_lookup_search_and_relationships(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "index.sqlite3"
            build_database(ROOT, db_path)
            store = KnowledgeStore(db_path)
            # Compound phrases are composed from individually reusable
            # concepts, not stored as duplicate dictionary entries.
            self.assertIsNone(store.get("bio:pyrimidine-deoxyribonucleotide"))
            self.assertEqual(store.resolve("pyrimidine"), ["chem:pyrimidine"])
            self.assertEqual(store.resolve("deoxyribonucleotide"), ["bio:deoxyribonucleotide"])
            pyrimidine = store.get("chem:pyrimidine")
            nucleotide = store.get("bio:deoxyribonucleotide")
            self.assertIn("nitrogen", pyrimidine["definition"])
            self.assertIn("deoxyribose", nucleotide["definition"])
            self.assertEqual(pyrimidine["status"], "source_checked")
            self.assertTrue(pyrimidine["sources"])
            self.assertTrue(nucleotide["sources"])
            self.assertEqual(store.resolve("DNA"), ["bio:dna"])
            self.assertEqual(store.resolve("deoxyribonucleic acid"), ["bio:dna"])
            self.assertIsNone(store.get("bio:not_real"))
            matches = {x["id"] for x in store.search("pyrimidine")}
            self.assertIn("chem:pyrimidine", matches)
            self.assertNotIn("bio:pyrimidine-deoxyribonucleotide", matches)
            with closing(sqlite3.connect(db_path)) as db:
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_repeated_atomic_rebuild_and_readers_release_handles(self):
        # Windows forbids replacing or deleting any SQLite file still opened
        # by this process, unlike Linux. A second build exposes that bug.
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "knowledge.sqlite3"
            first = build_database(ROOT, db_path)
            self.assertEqual(first, db_path)
            store = KnowledgeStore(first)
            self.assertEqual(store.get("bio:dna")["id"], "bio:dna")
            self.assertEqual(store.resolve("DNA"), ["bio:dna"])
            self.assertTrue(store.search("pyrimidine"))
            second = build_database(ROOT, db_path)
            self.assertEqual(second, db_path)
            self.assertEqual(store.get("bio:dna")["id"], "bio:dna")
            db_path.unlink()
            self.assertFalse(db_path.exists())

    def test_reject_invalid_relation_and_preserve_existing_compiled_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "concepts").mkdir()
            (root / "sources.json").write_text((ROOT / "sources.json").read_text(encoding="utf-8"), encoding="utf-8")
            src = json.loads((ROOT / "concepts" / "bio" / "nucleotide.json").read_text(encoding="utf-8"))
            src["relations"] = []
            (root / "concepts" / "nucleotide.json").write_text(json.dumps(src), encoding="utf-8")
            dest = root / "knowledge.sqlite3"
            build_database(root, dest)
            original = dest.read_bytes()
            src["relations"] = [{"type": "related", "target": "bio:not-real"}]
            (root / "concepts" / "nucleotide.json").write_text(json.dumps(src), encoding="utf-8")
            with self.assertRaises(KnowledgeError):
                build_database(root, dest)
            self.assertEqual(original, dest.read_bytes())

    def test_unreviewed_content_cannot_claim_reviewed_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "concepts").mkdir()
            (root / "sources.json").write_text((ROOT / "sources.json").read_text(encoding="utf-8"), encoding="utf-8")
            src = json.loads((ROOT / "concepts" / "bio" / "nucleotide.json").read_text(encoding="utf-8"))
            src["status"] = "reviewed"
            src["relations"] = []
            (root / "concepts" / "nucleotide.json").write_text(json.dumps(src), encoding="utf-8")
            with self.assertRaisesRegex(KnowledgeError, "review record"):
                read_concepts(root)

    def test_empty_search_and_missing_index_are_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = KnowledgeStore(Path(tmp) / "none.db")
            with self.assertRaises(FileNotFoundError):
                store.get("bio:dna")
            path = build_database(ROOT, Path(tmp) / "index.sqlite3")
            store = KnowledgeStore(path)
            self.assertEqual(store.search("   "), [])
            with self.assertRaises(ValueError):
                store.get("bio:dna", "imaginary")


if __name__ == "__main__":
    unittest.main()

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

    def test_long_form_protein_articles_roundtrip_through_sqlite(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = build_database(ROOT, Path(tmp) / "protein-articles.sqlite3")
            store = KnowledgeStore(db_path)
            for identifier in (
                "bio:protein", "bio:protein-folding",
                "bio:protein-domain", "bio:protein-subunit",
            ):
                with self.subTest(concept=identifier):
                    short = store.get(identifier, "simple")
                    scientific = store.get(identifier, "scientific")
                    self.assertIsNotNone(short)
                    self.assertEqual(short["definition"], next(
                        item["definitions"]["simple"] for item in read_concepts(ROOT)
                        if item["id"] == identifier
                    ))
                    self.assertGreaterEqual(len(short["article"]), 2)
                    self.assertEqual(short["article"], scientific["article"])
                    for section in short["article"]:
                        self.assertTrue(section["heading"])
                        self.assertTrue(section["paragraphs"])
                        self.assertTrue(set(section["sources"]).issubset(
                            {source["id"] for source in short["sources"]}))

    def test_protein_article_illustration_ids_roundtrip_through_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = build_database(ROOT, Path(tmp) / "illustrated.sqlite3")
            article = KnowledgeStore(db_path).get("bio:protein")["article"]
            illustrations = [
                section["illustration"] for section in article
                if "illustration" in section
            ]
            self.assertEqual(
                illustrations,
                ["protein-peptide-chain", "protein-structure-levels"],
            )
            self.assertTrue(all(
                section["sources"] for section in article
            ))

    def test_invalid_external_image_reference_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "concepts").mkdir()
            (root / "sources.json").write_text(
                (ROOT / "sources.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            raw = next(item for item in read_concepts(ROOT)
                       if item["id"] == "bio:protein")
            raw = json.loads(json.dumps(raw))
            raw["relations"] = []
            raw["article"][0]["illustration"] = "https://example.com/image.png"
            (root / "concepts" / "protein.json").write_text(
                json.dumps(raw), encoding="utf-8",
            )
            with self.assertRaisesRegex(KnowledgeError, "illustration ID"):
                read_concepts(root)

    def test_old_compiled_knowledge_index_still_supports_short_definitions(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = build_database(ROOT, Path(tmp) / "old.sqlite3")
            with closing(sqlite3.connect(db_path)) as db, db:
                db.execute("DROP TABLE articles")
                db.execute("PRAGMA user_version = 1")
            concept = KnowledgeStore(db_path).get("bio:protein")
            self.assertTrue(concept["definition"])
            self.assertEqual(concept["article"], [])

    def test_reject_unattributed_full_article_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "concepts").mkdir()
            (root / "sources.json").write_text(
                (ROOT / "sources.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            raw = next(item for item in read_concepts(ROOT)
                       if item["id"] == "bio:protein")
            raw = json.loads(json.dumps(raw))
            raw["relations"] = []
            raw["article"][0]["sources"] = ["ref:missing"]
            (root / "concepts" / "protein.json").write_text(
                json.dumps(raw), encoding="utf-8",
            )
            with self.assertRaisesRegex(KnowledgeError, "article sections must cite"):
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

"""Review queue is deterministic, evidence-aware, and never publishes drafts."""
from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from knowledge.knowledge_store import ROOT, KnowledgeError, build_database, KnowledgeStore
from knowledge.term_review import (collect_candidates, export_review_queue,
                                   import_completed_entries)


class TermReviewTests(unittest.TestCase):
    def test_collect_existing_articles_and_skip_defined_terms(self):
        with TemporaryDirectory() as temp:
            articles = Path(temp) / "articles"
            articles.mkdir()
            sample = {
                "title": "Biology of proteins",
                "key_terms": [
                    {"term": "Ribosome", "definition": "Existing"},
                    {"term": "Adenylate kinase", "definition": "An enzyme that exchanges phosphates"},
                    {"term": "Protonation state", "definition": "A molecule's hydrogenation state"},
                ],
                "sources": [
                    {"id": "n", "url": "https://www.ncbi.nlm.nih.gov/books/NBK9879/"}
                ],
            }
            (articles / "1.json").write_text(json.dumps(sample), encoding="utf-8")
            sample["title"] = "Metabolism"
            sample["key_terms"] = [
                {"term": "adenylate   kinase", "definition": "Second article's wording"},
                {"term": "Protein", "definition": "Existing"}
            ]
            (articles / "2.json").write_text(json.dumps(sample), encoding="utf-8")
            rows = collect_candidates(articles, root=ROOT)
            self.assertEqual(len(rows), 2)
            by_term = {row["term"].casefold(): row for row in rows}
            self.assertIn("adenylate kinase", by_term)
            self.assertEqual(by_term["adenylate kinase"]["occurrences"], 2)
            self.assertEqual(by_term["adenylate kinase"]["articles"],
                             "Biology of proteins | Metabolism")
            self.assertIn("ncbi.nlm.nih.gov",
                          by_term["adenylate kinase"]["possible_article_references"])
            self.assertEqual(by_term["adenylate kinase"]["verified_source_ids"], "")
            self.assertEqual(by_term["adenylate kinase"]["simple_definition"], "")
            self.assertNotIn("ribosome", by_term)
            self.assertNotIn("protein", by_term)

    def test_export_has_editable_review_columns_and_no_changes_to_sources(self):
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            article_dir = directory / "articles"
            article_dir.mkdir()
            (article_dir / "one.json").write_text(json.dumps({
                "title": "Molecular structure",
                "key_terms": [
                    {"term": "Hydration shell", "definition": "Surrounding water molecules"}
                ]
            }), encoding="utf-8")
            out, count = export_review_queue(
                directory / "build" / "editorial.csv",
                article_root=article_dir, root=ROOT,
            )
            self.assertEqual(count, 1)
            with out.open(encoding="utf-8-sig", newline="") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(rows[0]["term"], "Hydration shell")
            self.assertIn("simple_definition", rows[0])
            self.assertIn("verified_source_ids", rows[0])
            self.assertIn("review_notes", rows[0])
            self.assertEqual(rows[0]["concept_id"], "")
            self.assertEqual(rows[0]["verified_source_ids"], "")

    def test_batch_import_previews_then_creates_drafts_not_public_definitions(self):
        with TemporaryDirectory() as temp:
            root = Path(temp) / "knowledge"
            shutil.copytree(ROOT / "concepts", root / "concepts")
            shutil.copy2(ROOT / "sources.json", root / "sources.json")
            csv_file = Path(temp) / "review.csv"
            fieldnames = (
                "term", "concept_id", "simple_definition",
                "scientific_definition", "verified_source_ids", "review_notes",
            )
            with csv_file.open("w", encoding="utf-8", newline="") as out:
                writer = csv.DictWriter(out, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerow({
                    "term": "Hydration shell", "concept_id": "chem:hydration-shell",
                    "simple_definition": "Water molecules near a dissolved particle.",
                    "scientific_definition": "A local arrangement of solvent water molecules.",
                    "verified_source_ids": "ref:openstax-nucleic",
                    "review_notes": "Editorial draft for review, not verified.",
                })
                writer.writerow({"term": "Not finished"})
            dest = root / "concepts" / "chem" / "hydration-shell.json"
            prepared = import_completed_entries(csv_file, root=root)
            self.assertEqual(len(prepared), 1)
            self.assertEqual(prepared[0]["status"], "draft")
            self.assertFalse(dest.exists())
            imported = import_completed_entries(csv_file, root=root, apply=True)
            self.assertEqual(len(imported), 1)
            self.assertTrue(dest.exists())
            db_path = build_database(root, Path(temp) / "index.sqlite3")
            store = KnowledgeStore(db_path)
            self.assertEqual(store.get("chem:hydration-shell")["status"], "draft")
            self.assertFalse(any(
                r["id"] == "chem:hydration-shell"
                for r in store.search("Hydration shell")
            ))
            with self.assertRaises(KnowledgeError):
                import_completed_entries(csv_file, root=root)

    def test_batch_import_rejects_missing_citation_and_unreviewed_publish(self):
        with TemporaryDirectory() as temp:
            csv_file = Path(temp) / "review.csv"
            with csv_file.open("w", encoding="utf-8", newline="") as out:
                writer = csv.DictWriter(out, fieldnames=[
                    "term", "concept_id", "simple_definition",
                    "scientific_definition", "verified_source_ids", "review_notes",
                ])
                writer.writeheader()
                writer.writerow({
                    "term": "Unverified reaction", "concept_id": "chem:unverified-reaction",
                    "simple_definition": "Tentative statement.",
                    "scientific_definition": "An explanatory hypothesis.",
                    "verified_source_ids": "ref:nonexistent",
                    "review_notes": "",
                })
            with self.assertRaisesRegex(KnowledgeError, "unknown source"):
                import_completed_entries(csv_file)
            content = csv_file.read_text()
            csv_file.write_text(content.replace("ref:nonexistent", "ref:openstax-nucleic"))
            with self.assertRaisesRegex(KnowledgeError, "reviewer notes required"):
                import_completed_entries(csv_file, source_checked=True)

    def test_repository_articles_produce_reproducible_queue(self):
        original = collect_candidates()
        repeated = collect_candidates()
        self.assertEqual(original, repeated)
        # If all existing Learn terms are already defined, an empty queue is
        # also correct; this test must not enforce a guessed article count.
        self.assertEqual(len({row["term"].casefold() for row in original}),
                         len(original))


if __name__ == "__main__":
    unittest.main()

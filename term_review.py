"""Build a deduplicated editorial queue from terminology used in Learn articles.

The queue is *not* scientific evidence or a published dictionary. It is a
reproducible backlog of terms for humans to research, define and source-check.
No AI, network requests, Pygame, or external dependencies.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from knowledge.knowledge_store import (
    ROOT, IDENTIFIER, KnowledgeError, read_concepts, read_sources,
)

PROJECT_ROOT = ROOT.parent
ARTICLE_ROOT = PROJECT_ROOT / "learn" / "molecules"
DEFAULT_QUEUE = ROOT / "build" / "term_review_queue.csv"
QUEUE_FIELDS = (
    "term", "occurrences", "articles", "example_definition",
    "possible_article_references", "concept_id", "simple_definition",
    "scientific_definition", "verified_source_ids", "review_notes",
)


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).strip()).casefold()


def existing_labels(root: Path = ROOT) -> set[str]:
    """Skip all canonical names and synonyms; never multiply known concepts."""
    concepts = read_concepts(root)
    return {
        _normalized(label)
        for concept in concepts
        for label in [concept["name"], *concept.get("aliases", [])]
    }


def collect_candidates(article_root: Path = ARTICLE_ROOT, *, root: Path = ROOT) -> list[dict]:
    """Collect authored key terms, not arbitrary guessed word combinations.

    Sources present in an article are retained as *leads*, never automatically
    accepted as support for a specific definition.
    """
    known = existing_labels(root)
    candidates: dict[str, dict] = {}
    for file in sorted(Path(article_root).rglob("*.json")):
        try:
            article = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"Cannot parse educational article {file}: {exc}") from exc
        if not isinstance(article, dict):
            continue
        terms = article.get("key_terms", ())
        if not isinstance(terms, list):
            continue
        article_name = str(article.get("title") or file.stem).strip()
        source_urls = sorted({
            source.get("url", "")
            for source in article.get("sources", [])
            if isinstance(source, dict)
            and isinstance(source.get("url"), str)
            and source["url"].startswith("https://")
        })
        for term in terms:
            if not isinstance(term, dict):
                continue
            name = re.sub(r"\s+", " ", str(term.get("term") or "")).strip()
            key = _normalized(name)
            if not key or key in known:
                continue
            if len(name) > 120 or len(name.split()) > 7:
                continue
            if key not in candidates:
                candidates[key] = {
                    "term": name, "occurrences": 0, "article_names": set(),
                    "example_definition": str(term.get("definition") or "").strip(),
                    "possible_article_references": set(),
                }
            item = candidates[key]
            item["occurrences"] += 1
            item["article_names"].add(article_name)
            item["possible_article_references"].update(source_urls)
    return [
        {
            "term": item["term"],
            "occurrences": item["occurrences"],
            "articles": " | ".join(sorted(item["article_names"])),
            "example_definition": item["example_definition"],
            "possible_article_references": " | ".join(
                sorted(item["possible_article_references"])
            ),
            "concept_id": "",
            "simple_definition": "",
            "scientific_definition": "",
            "verified_source_ids": "",
            "review_notes": "",
        }
        for item in sorted(
            candidates.values(),
            key=lambda item: (-item["occurrences"], item["term"].casefold()),
        )
    ]


def export_review_queue(
    output: Path = DEFAULT_QUEUE, *,
    article_root: Path = ARTICLE_ROOT, root: Path = ROOT,
) -> tuple[Path, int]:
    """Write an Excel/LibreOffice-friendly CSV to the ignored build directory."""
    rows = collect_candidates(article_root, root=root)
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=QUEUE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return destination, len(rows)


def import_completed_entries(
    csv_path: Path, *, root: Path = ROOT, apply: bool = False,
    source_checked: bool = False,
) -> list[dict]:
    """Validate completed editor rows and optionally save source JSON.

    Unfinished rows are ignored. A partly filled row is an error. Existing
    labels/IDs and missing source references are rejected before any writes.
    Imported records default to DRAFT; source-checked publication requires
    a separate explicit flag and human-written review notes.
    """
    references = read_sources(root)
    original = read_concepts(root)
    existing_ids = {record["id"] for record in original}
    existing_names = existing_labels(root)
    new_ids, new_names = set(), set()
    ready = []
    required = (
        "concept_id", "term", "simple_definition",
        "scientific_definition", "verified_source_ids",
    )
    with Path(csv_path).open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames or not set(required).issubset(reader.fieldnames):
            raise KnowledgeError("Import CSV missing required editorial columns")
        for number, row in enumerate(reader, start=2):
            if not str(row.get("concept_id") or "").strip() and not any(
                str(row.get(field) or "").strip()
                for field in ("simple_definition", "scientific_definition", "verified_source_ids")
            ):
                continue  # Incomplete queue entry: not ready for publication.
            values = {field: str(row.get(field) or "").strip() for field in required}
            if not all(values.values()):
                raise KnowledgeError(f"Row {number}: incomplete concept or source fields")
            ident = values["concept_id"]
            if not IDENTIFIER.fullmatch(ident):
                raise KnowledgeError(f"Row {number}: invalid concept identifier {ident!r}")
            name = values["term"]
            name_key = _normalized(name)
            if ident in existing_ids or ident in new_ids:
                raise KnowledgeError(f"Row {number}: duplicate concept ID {ident}")
            if name_key in existing_names or name_key in new_names:
                raise KnowledgeError(f"Row {number}: already-defined term {name}")
            source_ids = [
                value.strip() for value in values["verified_source_ids"].split(";")
                if value.strip()
            ]
            if not source_ids or len(source_ids) != len(set(source_ids)):
                raise KnowledgeError(f"Row {number}: invalid or duplicate source references")
            if any(source_id not in references for source_id in source_ids):
                raise KnowledgeError(f"Row {number}: unknown source reference")
            note = str(row.get("review_notes") or "").strip()
            if source_checked and not note:
                raise KnowledgeError(
                    f"Row {number}: reviewer notes required for source-checked status"
                )
            entry = {
                "schema_version": 1, "id": ident, "name": name,
                "aliases": [], "definitions": {
                    "simple": values["simple_definition"],
                    "scientific": values["scientific_definition"],
                },
                "sources": source_ids, "relations": [],
                "status": "source_checked" if source_checked else "draft",
            }
            if note:
                entry["editorial_note"] = note
            ready.append(entry)
            new_ids.add(ident)
            new_names.add(name_key)

    if apply:
        for entry in ready:
            domain, slug = entry["id"].split(":", 1)
            destination = Path(root) / "concepts" / domain / (slug + ".json")
            if destination.exists():
                raise KnowledgeError(f"Refusing to overwrite existing file: {destination}")
        for entry in ready:
            domain, slug = entry["id"].split(":", 1)
            destination = Path(root) / "concepts" / domain / (slug + ".json")
            destination.parent.mkdir(parents=True, exist_ok=True)
            # Mode x means an unexpected duplicate never overwrites any
            # existing scientific record.
            with destination.open("x", encoding="utf-8") as out:
                json.dump(entry, out, ensure_ascii=False, indent=2)
                out.write("\n")
    return ready


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discover missing authored scientific terms for editorial review"
    )
    parser.add_argument("--articles", type=Path, default=ARTICLE_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--top", type=int, default=15)
    parser.add_argument("--import-csv", type=Path,
                        help="Validate completed definition rows in the review CSV")
    parser.add_argument("--apply", action="store_true",
                        help="Write validated records (default is preview only)")
    parser.add_argument("--source-checked", action="store_true",
                        help="Explicitly attest that each imported definition and its "
                             "registered sources were manually checked")
    args = parser.parse_args()
    if args.import_csv:
        reviewed = import_completed_entries(
            args.import_csv, apply=args.apply, source_checked=args.source_checked,
        )
        print(f"{'Imported' if args.apply else 'Validated'} "
              f"{len(reviewed)} completed scientific definitions "
              f"({'source_checked' if args.source_checked else 'draft'})")
        return
    rows = collect_candidates(args.articles)
    path, total = export_review_queue(args.output, article_root=args.articles)
    print(f"Queued {total} unique undefined authored key terms: {path}")
    for row in rows[:max(0, args.top)]:
        print(f"  {row['occurrences']:>3}  {row['term']}")


if __name__ == "__main__":
    main()

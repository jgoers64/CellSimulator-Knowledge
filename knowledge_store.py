"""Portable, versioned, offline scientific knowledge store.

Source JSON is authoritative; SQLite is a reproducible, disposable read index.
No runtime network, AI, Pygame, or simulation dependencies.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
import re
import sqlite3
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
SOURCE_DIR = ROOT / "concepts"
DEFAULT_DB = ROOT / "build" / "knowledge.sqlite3"
SCHEMA_VERSION = 1
INDEX_VERSION = 2  # optional extended article content in compiled SQLite
LONGFORM_INDEX_VERSION = 3  # chapter-length source documents in compiled SQLite
IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*:[a-z0-9][a-z0-9_.-]*$")
STATUS = {"draft", "source_checked", "reviewed", "deprecated"}
LEVELS = {"simple", "scientific"}
RELATIONS = {"broader", "part_of", "related", "example_of", "has_part"}


class KnowledgeError(ValueError):
    pass


def _nonempty(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KnowledgeError(f"{label} must be nonempty text")
    return value.strip()


def _id(value, label: str) -> str:
    value = _nonempty(value, label)
    if not IDENTIFIER.fullmatch(value):
        raise KnowledgeError(f"Invalid {label}: {value!r}")
    return value


def read_sources(root: Path = ROOT) -> dict:
    path = root / "sources.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise KnowledgeError(f"Unsupported sources schema in {path}")
    result = {}
    for source in raw.get("sources", []):
        key = _id(source.get("id"), "source id")
        if key in result:
            raise KnowledgeError(f"Duplicate source {key}")
        url = _nonempty(source.get("url"), f"{key} URL")
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise KnowledgeError(f"{key}: HTTPS source URL required")
        result[key] = (_nonempty(source.get("label"), "source label"), url)
    return result


def read_concepts(root: Path = ROOT) -> list[dict]:
    sources = read_sources(root)
    found = {}
    for path in sorted((root / "concepts").rglob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        key = _id(raw.get("id"), "concept id")
        if key in found:
            raise KnowledgeError(f"Duplicate concept id: {key}")
        if raw.get("schema_version") != SCHEMA_VERSION:
            raise KnowledgeError(f"{path}: unsupported schema")
        name = _nonempty(raw.get("name"), f"{key} name")
        aliases = raw.get("aliases", [])
        if not isinstance(aliases, list) or any(not isinstance(x, str) or not x.strip() for x in aliases):
            raise KnowledgeError(f"{key}: aliases must contain strings")
        if len({x.casefold().strip() for x in [name, *aliases]}) != len([name, *aliases]):
            raise KnowledgeError(f"{key}: duplicate aliases")
        status = raw.get("status", "draft")
        if status not in STATUS:
            raise KnowledgeError(f"{key}: invalid review status")
        definitions = raw.get("definitions")
        if not isinstance(definitions, dict) or set(definitions) != LEVELS:
            raise KnowledgeError(f"{key}: both simple and scientific definitions required")
        for level in LEVELS:
            _nonempty(definitions[level], f"{key}.{level}")
        cited = raw.get("sources", [])
        if not isinstance(cited, list) or not cited or any(x not in sources for x in cited):
            raise KnowledgeError(f"{key}: cite registered sources")
        if len(set(cited)) != len(cited):
            raise KnowledgeError(f"{key}: duplicate citations")
        article = raw.get("article", [])
        if not isinstance(article, list) or len(article) > 16:
            raise KnowledgeError(f"{key}: article must be a list of at most 16 sections")
        section_titles = set()
        for section in article:
            if not isinstance(section, dict):
                raise KnowledgeError(f"{key}: article sections must be objects")
            heading = _nonempty(section.get("heading"), f"{key} article heading")
            if heading.casefold() in section_titles:
                raise KnowledgeError(f"{key}: duplicate article heading {heading}")
            section_titles.add(heading.casefold())
            paragraphs = section.get("paragraphs")
            if (not isinstance(paragraphs, list) or not paragraphs
                    or len(paragraphs) > 8):
                raise KnowledgeError(f"{key}: article paragraphs must be a nonempty list")
            for paragraph in paragraphs:
                _nonempty(paragraph, f"{key} article paragraph")
            if "illustration" in section:
                # Only stable offline illustration IDs are allowed. External
                # image URLs or filesystem paths never enter the data index.
                illustration = section["illustration"]
                if (not isinstance(illustration, str)
                        or re.fullmatch(r"[a-z][a-z0-9-]{1,63}", illustration) is None):
                    raise KnowledgeError(f"{key}: invalid article illustration ID")
            refs = section.get("sources", [])
            if not isinstance(refs, list) or not refs or any(ref not in cited for ref in refs):
                raise KnowledgeError(f"{key}: article sections must cite concept sources")
        if "article_file" in raw:
            # A concept may have one complete chapter-length source document.
            # Paths must stay inside this repository's articles directory.
            value = _nonempty(raw["article_file"], f"{key} article_file")
            if (re.fullmatch(r"articles/[a-z0-9][a-z0-9_-]*\\.md", value) is None
                    or (root / value).is_symlink()):
                raise KnowledgeError(f"{key}: invalid article_file path")
            source_text = (root / value).read_text(encoding="utf-8")
            if not source_text.startswith("# ") or len(source_text) > 200_000:
                raise KnowledgeError(f"{key}: invalid article_file content")
        if status == "reviewed" and not raw.get("review"):
            raise KnowledgeError(f"{key}: reviewed concepts require a review record")
        if status == "reviewed":
            record = raw["review"]
            for field in ("reviewer", "date", "basis"):
                _nonempty(record.get(field), f"{key}.review.{field}")
        relations = raw.get("relations", [])
        if not isinstance(relations, list):
            raise KnowledgeError(f"{key}: relations must be a list")
        for edge in relations:
            if edge.get("type") not in RELATIONS:
                raise KnowledgeError(f"{key}: unsupported relation {edge!r}")
            _id(edge.get("target"), "relation target")
        found[key] = raw
    if not found:
        raise KnowledgeError("No concept records found")
    for key, raw in found.items():
        for edge in raw.get("relations", []):
            if edge["target"] not in found:
                raise KnowledgeError(f"{key}: missing target {edge['target']}")
    return [found[k] for k in sorted(found)]


def _create_schema(db: sqlite3.Connection) -> None:
    db.executescript("""
        PRAGMA foreign_keys = ON;
        CREATE TABLE concepts (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL,
            schema_version INTEGER NOT NULL
        );
        CREATE TABLE definitions (
            concept_id TEXT NOT NULL REFERENCES concepts(id),
            level TEXT NOT NULL, text TEXT NOT NULL,
            PRIMARY KEY (concept_id, level)
        );
        CREATE TABLE labels (
            label TEXT NOT NULL COLLATE NOCASE,
            concept_id TEXT NOT NULL REFERENCES concepts(id),
            is_primary INTEGER NOT NULL,
            PRIMARY KEY (label, concept_id)
        );
        CREATE INDEX labels_lookup ON labels(label);
        CREATE TABLE sources (id TEXT PRIMARY KEY, label TEXT NOT NULL, url TEXT NOT NULL);
        CREATE TABLE articles (
            concept_id TEXT PRIMARY KEY REFERENCES concepts(id), content TEXT NOT NULL
        );
        CREATE TABLE longform_articles (
            concept_id TEXT PRIMARY KEY REFERENCES concepts(id), markdown TEXT NOT NULL
        );
        CREATE TABLE citations (
            concept_id TEXT NOT NULL REFERENCES concepts(id),
            source_id TEXT NOT NULL REFERENCES sources(id),
            PRIMARY KEY (concept_id, source_id)
        );
        CREATE TABLE relationships (
            source_id TEXT NOT NULL REFERENCES concepts(id),
            kind TEXT NOT NULL, target_id TEXT NOT NULL REFERENCES concepts(id),
            PRIMARY KEY (source_id, kind, target_id)
        );
        CREATE INDEX relationships_target ON relationships(target_id);
        CREATE TABLE reviews (
            concept_id TEXT PRIMARY KEY REFERENCES concepts(id),
            reviewer TEXT NOT NULL, reviewed_on TEXT NOT NULL, basis TEXT NOT NULL
        );
        CREATE VIRTUAL TABLE concept_search USING fts5(concept_id UNINDEXED, name, aliases, tokenize='unicode61');
        PRAGMA user_version = 3;
    """)


def build_database(root: Path = ROOT, destination: Path | None = None) -> Path:
    """Validate *all* records, build atomically, and leave previous DB on error."""
    root = Path(root)
    target = Path(destination) if destination is not None else root / "build" / "knowledge.sqlite3"
    concepts, sources = read_concepts(root), read_sources(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(prefix=".knowledge-", suffix=".sqlite3", dir=target.parent, delete=False) as temp:
        temp_path = Path(temp.name)
    try:
        # sqlite3.Connection.__exit__ only commits/rolls back; it does NOT
        # close the underlying file handle. Windows requires that handle to
        # be closed before os.replace() or unlink() can operate on the DB.
        with closing(sqlite3.connect(temp_path)) as db, db:
            _create_schema(db)
            for key, (label, url) in sources.items():
                db.execute("INSERT INTO sources VALUES (?,?,?)", (key, label, url))
            for raw in concepts:
                key, name = raw["id"], raw["name"]
                db.execute("INSERT INTO concepts VALUES (?,?,?,?)", (key, name, raw.get("status", "draft"), 1))
                for level, value in raw["definitions"].items():
                    db.execute("INSERT INTO definitions VALUES (?,?,?)", (key, level, value))
                for is_primary, label in [(1, name), *[(0, x) for x in raw.get("aliases", [])]]:
                    db.execute("INSERT INTO labels VALUES (?,?,?)", (label, key, is_primary))
                for source_id in raw["sources"]:
                    db.execute("INSERT INTO citations VALUES (?,?)", (key, source_id))
                if raw.get("article"):
                    db.execute(
                        "INSERT INTO articles VALUES (?, ?)",
                        (key, json.dumps(raw["article"], ensure_ascii=False)),
                    )
                if raw.get("article_file"):
                    article_text = (root / raw["article_file"]).read_text(encoding="utf-8")
                    db.execute(
                        "INSERT INTO longform_articles VALUES (?, ?)",
                        (key, article_text),
                    )
                if raw.get("status") == "reviewed":
                    review = raw["review"]
                    db.execute("INSERT INTO reviews VALUES (?,?,?,?)",
                               (key, review["reviewer"], review["date"], review["basis"]))
                db.execute("INSERT INTO concept_search VALUES (?,?,?)", (key, name, " ".join(raw.get("aliases", []))))
            # Relationship targets may sort after their sources. Insert edges
            # only after *all* concept IDs exist to preserve foreign keys.
            for raw in concepts:
                for relation in raw.get("relations", []):
                    db.execute("INSERT INTO relationships VALUES (?,?,?)",
                               (raw["id"], relation["type"], relation["target"]))
            if db.execute("PRAGMA foreign_key_check").fetchall():
                raise KnowledgeError("Foreign-key check failed")
        temp_path.replace(target)
    finally:
        temp_path.unlink(missing_ok=True)
    return target


class KnowledgeStore:
    """SQLite adapter. Queries never read JSON or perform a network request."""

    def __init__(self, path: Path = DEFAULT_DB):
        self.path = Path(path)

    def _connect(self):
        if not self.path.is_file():
            raise FileNotFoundError(f"Knowledge index missing: {self.path}. Build it first.")
        uri = f"file:{self.path.resolve().as_posix()}?mode=ro"
        return sqlite3.connect(uri, uri=True)

    def get(self, concept_id: str, level: str = "simple") -> dict | None:
        if level not in LEVELS:
            raise ValueError("level must be simple or scientific")
        with closing(self._connect()) as db:
            row = db.execute(
                """SELECT c.id,c.name,c.status,d.text FROM concepts c
                   JOIN definitions d ON d.concept_id=c.id AND d.level=?
                   WHERE c.id=?""", (level, concept_id)
            ).fetchone()
            if not row:
                return None
            cites = db.execute(
                """SELECT s.id,s.label,s.url FROM citations cs JOIN sources s ON s.id=cs.source_id
                   WHERE cs.concept_id=? ORDER BY s.id""", (concept_id,)
            ).fetchall()
            relations = db.execute(
                "SELECT kind,target_id FROM relationships WHERE source_id=? ORDER BY kind,target_id",
                (concept_id,)
            ).fetchall()
            article = []
            # Pre-upgrade SQLite indexes remain usable until an explicit rebuild.
            if db.execute("PRAGMA user_version").fetchone()[0] >= INDEX_VERSION:
                article_row = db.execute(
                    "SELECT content FROM articles WHERE concept_id=?", (concept_id,)
                ).fetchone()
                if article_row:
                    article = json.loads(article_row[0])
            article_markdown = ""
            if db.execute("PRAGMA user_version").fetchone()[0] >= LONGFORM_INDEX_VERSION:
                longform_row = db.execute(
                    "SELECT markdown FROM longform_articles WHERE concept_id=?",
                    (concept_id,),
                ).fetchone()
                if longform_row:
                    article_markdown = longform_row[0]
            return {
                "id": row[0], "name": row[1], "status": row[2], "definition": row[3],
                "level": level, "article": article,
                "article_markdown": article_markdown,
                "sources": [{"id": x[0], "label": x[1], "url": x[2]} for x in cites],
                "relations": [{"type": x[0], "target": x[1]} for x in relations],
            }

    def resolve(self, label: str) -> list[str]:
        """Ambiguities return multiple IDs; never guess which 'base' is meant."""
        with closing(self._connect()) as db:
            return [row[0] for row in db.execute(
                "SELECT concept_id FROM labels WHERE label=? ORDER BY is_primary DESC,concept_id",
                (label.strip(),)
            ).fetchall()]

    def search(self, query: str, limit: int = 20) -> list[dict]:
        query = str(query or "").strip()
        if not query:
            return []
        limit = max(1, min(100, int(limit)))
        # Parameterized FTS query; quote user terms as literals (not FTS operators).
        escaped = query.replace('"', '""')
        with closing(self._connect()) as db:
            return [
                {"id": row[0], "name": row[1], "status": row[2]}
                for row in db.execute(
                    """SELECT c.id,c.name,c.status FROM concept_search f
                       JOIN concepts c ON c.id=f.concept_id
                       WHERE concept_search MATCH ?
                       AND c.status IN ('source_checked', 'reviewed')
                       ORDER BY rank LIMIT ?""",
                    ('"' + escaped + '"', limit)
                ).fetchall()
            ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and query the CellSimulator knowledge index")
    parser.add_argument("command", choices=["validate", "build", "search", "show"])
    parser.add_argument("query", nargs="?")
    parser.add_argument("--level", choices=sorted(LEVELS), default="simple")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    if args.command == "validate":
        print(f"Validated {len(read_concepts())} concepts and {len(read_sources())} sources")
    elif args.command == "build":
        print(f"Built {build_database(destination=args.db)}")
    else:
        store = KnowledgeStore(args.db)
        if not args.query:
            parser.error(f"{args.command} requires a query")
        value = store.search(args.query) if args.command == "search" else store.get(args.query, args.level)
        print(json.dumps(value, indent=2))


if __name__ == "__main__":
    main()

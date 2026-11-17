"""Explicit, source-backed concept links in educational prose.

Works against an indexed SQLite database. A million definitions do not need
to be loaded into a Python dictionary to annotate one paragraph.
"""
from __future__ import annotations

from contextlib import closing
from functools import lru_cache
import re
import sqlite3
from pathlib import Path

from knowledge.knowledge_store import DEFAULT_DB

_TOKEN = re.compile(r"[^\W_]+(?:['’′-][^\W_]+)*", re.UNICODE)
_MAX_WORDS = 4
_BATCH = 300


def _candidates(text: str):
    tokens = list(_TOKEN.finditer(text))
    candidates = {}
    for start_index, first in enumerate(tokens):
        for length in range(1, _MAX_WORDS + 1):
            end_index = start_index + length
            if end_index > len(tokens):
                break
            last = tokens[end_index - 1]
            value = text[first.start():last.end()]
            # Do not turn arbitrary punctuation-separated words into a phrase.
            # The source labels retain spelling, whitespace, and punctuation.
            if length > 1 and re.search(r"[^ \t\nA-Za-z0-9']", value):
                continue
            candidates.setdefault(value.casefold(), []).append(
                (start_index, end_index, first.start(), last.end())
            )
    return tokens, candidates


@lru_cache(maxsize=512)
def _match_cached(path_string: str, modified_ns: int, text: str, exclude_id: str):
    del modified_ns  # Used as a stable cache-invalidation key.
    _tokens, candidates = _candidates(text)
    if not candidates:
        return ()
    keys = list(candidates)
    matched = {}
    try:
        uri = f"file:{Path(path_string).resolve().as_posix()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as db:
            for index in range(0, len(keys), _BATCH):
                batch = keys[index:index + _BATCH]
                placeholders = ",".join("?" for _ in batch)
                rows = db.execute(
                    f"""SELECT l.label,l.concept_id FROM labels l
                        JOIN concepts c ON c.id=l.concept_id
                        WHERE l.label COLLATE NOCASE IN ({placeholders})
                        AND c.status IN ('source_checked','reviewed')""",
                    batch,
                )
                for label, concept_id in rows:
                    matched.setdefault(label.casefold(), set()).add(concept_id)
    except (sqlite3.Error, OSError):
        return ()

    proposals = []
    for key, occurrences in candidates.items():
        ids = matched.get(key)
        if not ids or len(ids) != 1:
            continue  # Ambiguous homonyms must not guess a scientific meaning.
        concept_id = next(iter(ids))
        if concept_id == exclude_id:
            continue  # Never link the definition's own term to itself.
        for first, end, start, stop in occurrences:
            proposals.append((first, -(end - first), start, stop, end, concept_id))

    # Longest phrase wins. E.g. link "peptide bond" as a unit rather than
    # overlapping smaller matches, with text offsets remaining exact.
    proposals.sort()
    accepted = []
    occupied = 0
    for first, neg_length, start, stop, end, concept_id in proposals:
        if first < occupied:
            continue
        accepted.append((start, stop, concept_id))
        occupied = end
    return tuple(accepted)


def find_concept_links(text: str, *, exclude_id: str = "", path: Path | None = None):
    """Return (start, end, id) without changing prose; no network/AI."""
    database = Path(path) if path is not None else DEFAULT_DB
    try:
        version = database.stat().st_mtime_ns
    except OSError:
        return ()
    return _match_cached(str(database), version, str(text or ""), str(exclude_id or ""))


__all__ = ["find_concept_links"]

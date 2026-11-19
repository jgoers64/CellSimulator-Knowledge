# CellSimulator Knowledge

Independent, source-backed scientific dictionary and concept database for [CellSimulator](https://github.com/jgoers64/CellSimulator).

Definitions, concepts, scientific references, database build tools and editorial review tools live here. Python simulation and UI remain in CellSimulator.

The repository is designed to be checked out as the `knowledge/` Git submodule in CellSimulator.

## Quick start (from CellSimulator)

```powershell
git submodule update --init --recursive
python -m knowledge.knowledge_store validate
python -m knowledge.knowledge_store build
python main.py
```

The compiled SQLite index is intentionally **not** committed; `knowledge/build/` is ignored.

## Dictionary definitions and learning articles

A **dictionary entry** supplies separate simple and scientific definitions,
with canonical concept IDs, source references, and related terms. These are used
by the floating glossary and quick lookup.

A **learning article** contains a textbook-style explanation. The Protein
article is `articles/protein.md`, linked by `"article_file"` in
`concepts/bio/protein.json`. It now has six organized chapters (Molecular
Composition, Protein Structure, Protein Folding and Dynamics, Biological
Functions, Protein Synthesis and Life Cycle, and Studying Proteins), a conclusion
and references. The reorganization retained the manuscript's original
scientific prose and all ten future-figure markers.

The compiled SQLite index is version **4**, adding a separate
`article_metadata` review record. **Definitions can be source-checked while
the full article is still a draft awaiting independent scientific review.**
The article's author credit, revision history, version and review information
are managed in the JSON source, not written into the compiled database by hand.

`python -m knowledge.knowledge_store build` validates the article and review
metadata, then compiles the source into the read-only index. The simulator
reads one chapter at a time; older indexes can still display their existing
definition and article content until rebuilt.

Figures use offline schematics where available. Additional figure descriptions
remain in the article as editorial placeholders; their scientific content is
not presented as independently verified research.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the editorial and review workflow.

## Editorial rules

Keep one entry per meaningful scientific concept, not every possible combination of words. Every entry must have a stable ID, simple and scientific explanations, sources and an editorial status. Research drafts are not displayed in the public dictionary.

See the detailed contributor and review workflow in [CONTRIBUTING.md](CONTRIBUTING.md).

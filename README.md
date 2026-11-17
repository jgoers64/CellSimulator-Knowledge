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

## Editorial rules

Keep one entry per meaningful scientific concept, not every possible combination of words. Every entry must have a stable ID, simple and scientific explanations, sources and an editorial status. Research drafts are not displayed in the public dictionary.

See the detailed contributor and review workflow in [CONTRIBUTING.md](CONTRIBUTING.md).

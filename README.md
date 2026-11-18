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

## Long-form chapter source files

The authoritative **Protein** lesson is `articles/protein.md`, a complete
user-authored educational manuscript with ten chapters, numbered subsections,
a conclusion, a bibliography and proposed figure locations. The source file is
preserved as written; the JSON entry `concepts/bio/protein.json` references it
using `"article_file": "articles/protein.md"`. The small popup definitions
remain separate.

`python -m knowledge.knowledge_store build` validates this path and compiles
the Markdown into a version-3 read-only SQLite index. The simulator retrieves
the compiled text and displays one chapter at a time. Previous version-1/2
indexes can still show concise definitions and the older short articles until
rebuilt. Do not manually edit the disposable SQLite file.

Figures are implemented in the parent simulator as offline, clearly labeled
schematics. The original author's future-visual notes remain intact here so
additional figures can be developed without losing their scientific intent.

## Editorial rules

Keep one entry per meaningful scientific concept, not every possible combination of words. Every entry must have a stable ID, simple and scientific explanations, sources and an editorial status. Research drafts are not displayed in the public dictionary.

See the detailed contributor and review workflow in [CONTRIBUTING.md](CONTRIBUTING.md).

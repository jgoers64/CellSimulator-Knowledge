# CellSimulator Knowledge — Editorial Guide

A versioned, portable scientific concept store. The **JSON concepts, Markdown
articles and references** are the editorial source of truth; the SQLite file
is a **rebuildable runtime index**, not the place to edit definitions.

This is the independent `CellSimulator-Knowledge` repository, consumed by
CellSimulator through the `knowledge/` Git submodule.

## Commands (from CellSimulator root)

```powershell
python -m knowledge.knowledge_store validate
python -m knowledge.knowledge_store build
python -m knowledge.knowledge_store search pyrimidine
python -m knowledge.knowledge_store show chem:pyrimidine
python -m unittest knowledge.tests.test_knowledge -v
```

Search uses SQLite FTS5. The read-only `KnowledgeStore` adapter exposes `get(id, level)`, `resolve(label)`, and `search(query, limit)`. It loads *only* requested definitions; it never loads all entries into RAM or makes network requests. Missing or ambiguous terms are reported rather than silently guessed.

## Two complementary educational formats

1. **Dictionary entries** in `concepts/<domain>/*.json` provide simple and
   scientific definitions, related concepts and verifiable source IDs. These
   power quick lookup and floating term definitions.
2. **Learning articles** in `articles/*.md` provide textbook-style chapters.
   The concept entry points to the article using `article_file`. Do not copy
   an entire lesson into a small popup definition.

An article can remain a scientific **draft** even when its short dictionary
definitions have been source-checked. Do not conflate the concept's `status`
with its distinct `article_metadata.status`.

## Editorial review workflow for long-form articles

Use `concepts/bio/protein.json` and `articles/protein.md` as the first
reference example. Each long-form article's optional `article_metadata` object
contains:

- `version` — the exact draft or approved article revision.
- `status` — `draft`, `source_checked`, or `reviewed`.
- `author` — a credited author or a clear "Attribution pending" placeholder.
- `updated_on` — the latest edit date (YYYY-MM-DD).
- `history` — ordered, dated entries recording version and actual changes.
- `review` — `null` until reviewed, then a record with `reviewer`,
  `date`, `basis`, and the exact `version` that was checked.

For source checks, inspect the specific claims against scientific references
and revise unsupported statements. For an independent review, obtain an actual
reviewer assessment, record its basis and date, and only then set
`article_metadata.status` to `reviewed`. The validator rejects missing
reviews and reviews tied to older versions. It validates the presence of
records, **not** the accuracy or independence of an asserted review.

The Protein manuscript was reorganized from ten chapters into six in the
November 2026 draft. Its original scientific paragraphs and ten planned
figure notes were retained. The review metadata explicitly remains
`draft`; neither a reorganization nor source listings constitute scientific
approval.

For future articles, aim for a concise definition, logical sequence from
molecular composition to biological mechanisms, well-labeled figures, source
references and a recorded revision history. Scientific illustrations must
distinguish experimental observations from models and simulations.

## How to add information

1. Create a new namespaced, permanent ID (for example `bio:dna`; never use a display label as an ID).
2. Add a concept JSON file under `concepts/<domain>/`, with `schema_version: 1`, `name`, `aliases`, two `definitions`, `sources`, `relations`, and `status`.
3. Register source references in `sources.json`. Cite the sources supporting the concept, not unrelated links. Write original explanations; don't paste copyrighted articles.
4. Run the validator and tests. References to nonexistent concepts and invalid source IDs are rejected. The build is atomic and preserves the previous database on validation failure.
5. Start with `draft`; use `source_checked` after checking content against referenced material. **Only use `reviewed` when a real review record (reviewer, date, basis) is recorded.** The validator confirms that records are present, **not** that claims are factually correct.

This seed now contains **31 source-checked but not yet independently peer-reviewed entries**, covering DNA, nucleotides, pyrimidine, cytosine, and thymine. No entry is labeled as scientifically certified. Source checking is not proof of 100% accuracy.

## Growing the dictionary from existing articles

We now have an editorial review pipeline for *authored scientific key terms*
that currently appear in CellSimulator's Learn articles but are not yet in
the knowledge database. This avoids indiscriminately defining every pair of
adjacent words, which would create an exponentially redundant dictionary.

From the CellSimulator root directory:

```powershell
# Generate a CSV review backlog; no source or database files are modified.
python -m knowledge.term_review --top 25
# The queue is written under knowledge/build/term_review_queue.csv.
```

The backlog contains term frequency, article titles, the original article's
example explanation, and **possible references** mentioned in those articles.
Those URLs are research leads, **not automatically verified citations**.

Editors fill `concept_id` (for example `bio:anticodon`),
`simple_definition`, `scientific_definition`, and `verified_source_ids`
(semicolon-separated IDs from `knowledge/sources.json`). Complete rows can
be checked without changing the repository:

```powershell
python -m knowledge.term_review --import-csv knowledge/build/term_review_queue.csv
# After review, create DRAFT concept JSON files:
python -m knowledge.term_review --import-csv knowledge/build/term_review_queue.csv --apply
# Only after manually checking each definition against its cited sources,
# recording meaningful review_notes, and verifying the batch:
python -m knowledge.term_review --import-csv knowledge/build/term_review_queue.csv --apply --source-checked
```

The last command only applies to records not already imported; do not run
both import commands for the same entries. Choose draft **or** source-checked
publication based on the actual state of review. The program validates IDs,
required descriptions, duplicate names, and registered citations before it
writes any concepts. It never overwrites existing concept files.

**Draft concepts do not appear in the public Dictionary search or clickable
term links.** Approval is a scientific/editorial decision, not an automatic
consequence of a script running successfully.

Five additional foundational source-checked concepts are also included:
ribonucleotide, ribose, phosphodiester bond, anticodon, and ribosomal RNA.
Their statements were checked against relevant OpenStax Biology 2e pages.
These concepts have not received independent peer review.

## Scaling

At first, keep human-reviewable JSON in Git and distribute compiled SQLite snapshots. At a much larger scale, put the same normalized logical schema in PostgreSQL or another storage backend behind the `get / resolve / search` interface. Keep revision history, signed releases, citation licenses, explicit concept IDs and provenance. A billion JSON files should never live in Git.

## Simulator integration (first stage)

The app's existing `sim/glossary_workspace.py` now consults the read-only knowledge index **only when a molecule has no dedicated Learn article**. Existing authored articles stay authoritative, and lookup failures never stop the viewer.

- Build the index once using `python -m knowledge.knowledge_store build`, then launch `python main.py`.
- `sim/knowledge_bridge.py` exposes `concept_by_id`, `concept_for_molecule`, and `concept_for_exact_label`. The bridge uses exact IDs or unambiguous labels; it never guesses a meaning.
- One explicit demonstration association maps `nucleotides/dna/b_dna_cg_1bna` to `bio:dna`. There are **no invented new molecular structures**.
- The Learn viewer now has an interactive **Dictionary** button. After compiling the index, click this button to search definitions, select Simple or Scientific, follow related concepts, and open source links. Matched **Key Terms** headings in existing Learn articles are also clickable. The glossary preview shows a contextual **Define** action when its exact molecule name matches a concept.
- Only explicitly authored Key Terms with a unique exact database match are highlighted; arbitrary text throughout every article is **not** automatically linked in this version. This avoids guessing ambiguous meanings. The compiled knowledge database is still a locally built, read-only file.

## Reusable concepts, not combinatorial entries

The phrase **pyrimidine deoxyribonucleotide** is not a standalone
dictionary record. A user can select **pyrimidine** and
**deoxyribonucleotide** independently. The term-linking engine identifies
both, retaining the meaning without multiplying combined entries as new
words appear.

## Clickable scientific terminology

The initial seven concepts have been expanded with **20 source-checked definitions**
covering amino acids, protein folding vocabulary, RNA, ribosomes, the genetic code,
base pairing, and elementary chemical bonds (31 total). These remain **source-checked,
not independently reviewed or guaranteed infallible**.

To activate the expanded dictionary on your computer:

```powershell
git pull
python -m knowledge.knowledge_store build
python main.py
```

Term linking is automatic for **exact, unambiguous registered labels** in the
Glossary preview, full Learn article paragraphs and key-term explanations, and
within Dictionary definitions. Clicking an underlined term opens the corresponding
scientific entry. The current entry's own term is not underlined in its definition.
Unrecognized phrases and ambiguous names are not linked. The renderer makes
read-only indexed SQLite lookups for terms in the current passage; it does not
load the entire encyclopedia into RAM. Adding a definition therefore does not
require manually editing existing molecule descriptions.

The source-backed annotation matcher uses word boundaries and longest-match
priority for multiword terms. It makes no AI inference, and underlining is a
navigation cue, **not** a claim that the fact has been independently verified.

## Limits of v1

- Proof-of-concept verified **data structure** and source attribution, not a full editorial review workflow or auto-importer.
- Data are English-only and do not yet have claim-level citations or recorded historical revisions beyond Git.
- It is a usable backend, not yet the final clickable highlighted-text panel.

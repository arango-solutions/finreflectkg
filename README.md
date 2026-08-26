# FinReflectKG on ArangoDB

A proof of concept that loads **[FinReflectKG](https://huggingface.co/datasets/domyn/FinReflectKG)** — a
financial knowledge graph extracted from S&P 500 10-K SEC filings (2014–2024) — into a managed
**ArangoDB 3.12.x Enterprise** cluster, and evaluates it for graph-query and natural-language /
GraphRAG-style query performance at scale.

Headline size: **17.5 M edges**, **3.1 M nodes**, **1.38 M deduplicated source-text chunks**
over **743 companies** (paper: [arXiv:2508.17906](https://arxiv.org/abs/2508.17906)).

> **Scope.** This repository is the **ETL, data model, and benchmarking harness** — code and
> documentation only. It does **not** contain the dataset itself; the pipeline downloads it from
> Hugging Face at build time. See [License & attribution](#license--attribution).

---

## What's here

| Area | Summary |
|---|---|
| **Data model** | A labeled property graph (Neo4j-aligned terminology): a single `Node` collection, a single `relations` edge collection, and a deduplicated `chunks` collection for source text. |
| **ETL** | DuckDB-based parquet → JSONL transform + `arangoimport` bulk load. Idempotent and resumable end-to-end. |
| **Indexing** | Vertex-centric (persistent) indexes on `relations` to prune typed 1-hop queries by edge type and far-end node type. |
| **Multi-distribution** | The same dataset built under three placements — a baseline single-shard db, a **OneShard** db, and a **Disjoint SmartGraph** db — for comparative scale benchmarking. |
| **Benchmarks** | Representative query classes (point lookup, typed 1-hop, supernode handling, k-hop paths, temporal slices, NL-grounding joins, label-rooted aggregations). |
| **Graph analytics** | PageRank/centrality, connected components, and community detection via the ArangoDB **Graph Analytics Engine (GAE)**, over the same `Node`/`relations` LPG. Deterministic base ([`scripts/analytics.py`](scripts/analytics.py)) is **implemented & verified** — PageRank + WCC run end-to-end on all 3.1 M nodes via `agentic-graph-analytics` (self-managed GAE), results in non-mutating `gae_<algorithm>` collections. An agentic **planning** layer ([`scripts/analytics_agentic.py`](scripts/analytics_agentic.py)) turns a business-requirements doc into GAE use cases end-to-end (which algorithms to run); the base layer executes them. See [`docs/PRD.md`](docs/PRD.md) §4.7. |
| **Docs** | A full PRD and supporting design/analysis docs under [`docs/`](docs/). |

See **[`docs/PRD.md`](docs/PRD.md)** for the authoritative design, goals, and current status.

---

## Data model

- **`Node`** (documents) — one per distinct `(name, type)` pair; `_key` is a deterministic hash of
  `name|type` (raw names contain characters illegal in ArangoDB keys).
- **`relations`** (edges) — one edge per source triple occurrence, preserving provenance and temporal
  bounds. Each edge carries `type`, `_fromType`, `_toType` (enabling the vertex-centric indexes),
  plus `startDate`, `endDate`, `ticker`, `year`, `chunkKey`, and other provenance fields.
- **`chunks`** (documents) — deduplicated source-text chunks (~4–5 GB deduplicated vs ~50 GB if
  inlined on every edge), referenced from edges via `chunkKey` for NL/GraphRAG grounding.

Two vertex-centric indexes are built **after** bulk load:

- `relations(_from, type, _toType)`
- `relations(_to, type, _fromType)`

> **Note (verified on 3.12.x cluster):** the VCIs accelerate **direct edge-collection queries**
> (`FOR e IN relations FILTER e._from == … AND e.type == … AND e._toType == …`), not pattern
> traversals. Write typed 1-hop neighborhood queries as direct edge queries; reserve pattern
> traversals for variable-depth pathfinding. Details in [`docs/load-report.md`](docs/load-report.md).

---

## Repository layout

```
docs/        PRD + design, analysis, load, sharding, and query-migration docs
scripts/     ETL, build, validation, benchmark, visualizer-setup, and BYOC packaging scripts
demo/        Time-travel visualizer (FastAPI + Cytoscape); packable for Arango BYOC
data/        local dataset artifacts (gitignored — created by the pipeline)
.env         connection + dataset config (gitignored — copy from .env.example)
```

---

## Prerequisites

- An **ArangoDB 3.12.x Enterprise** endpoint (OneShard, SmartGraph, and SatelliteCollections are
  Enterprise features). A 3-Coordinator / 3-DBServer / 3-Agent cluster was used for this POC.
- **Docker** (for the `arangodb` CE image, used purely as the `arangoimport` client).
- **Python 3** with a virtualenv at `.venv` (DuckDB is used for preprocessing).
- ~2 GB free to download the parquet shards; more for the staging JSONL.

---

## Setup

1. Create the virtualenv and install dependencies:

```bash
python3 -m venv .venv
.venv/bin/pip install -U pip duckdb python-arango huggingface_hub
```

2. Configure your connection by copying the example and filling in your own values:

```bash
cp .env.example .env
# then edit .env
```

`.env` is gitignored — keep secrets out of code and docs.

---

## Build

Rebuild the baseline database end-to-end with one command:

```bash
./scripts/rebuild_all.sh
```

This runs, in order: download → preprocess → provision db/collections → bulk import →
create indexes → validate (reconcile counts + VCI checks) → create the named graph →
install Graph Visualizer theme/queries/actions. Useful flags:

```bash
THREADS=8 ./scripts/rebuild_all.sh        # tune import parallelism
SKIP_DOWNLOAD=1 ./scripts/rebuild_all.sh  # reuse already-downloaded parquet
```

Every stage is idempotent, so an interrupted run is safe to re-run.

### Multi-distribution builds

The same dataset can be built under additional placements for comparative benchmarking:

```bash
./scripts/build_oneshard.sh   # OneShard database (FinReflectKgOneShard)
./scripts/build_smart.sh      # Disjoint SmartGraph database (FinReflectKgSmart)
```

See [`docs/multi-distribution-plan.md`](docs/multi-distribution-plan.md) for the design and rationale.

---

## Documentation

| Doc | Contents |
|---|---|
| [`docs/PRD.md`](docs/PRD.md) | Product/design requirements — the source of truth |
| [`docs/data-analysis.md`](docs/data-analysis.md) | Measured dataset characteristics |
| [`docs/data_dictionary.md`](docs/data_dictionary.md) | Canonical entity & relationship types |
| [`docs/etl-plan.md`](docs/etl-plan.md) | ETL design |
| [`docs/load-report.md`](docs/load-report.md) | As-loaded counts + VCI findings |
| [`docs/sharding-analysis.md`](docs/sharding-analysis.md) | Sharding analysis |
| [`docs/multi-distribution-plan.md`](docs/multi-distribution-plan.md) | OneShard + SmartGraph distributions |
| [`docs/schema-mapping.md`](docs/schema-mapping.md) | Source → graph schema mapping |
| [`docs/cypher-queries.md`](docs/cypher-queries.md) | Query migration / NL→AQL gold set |
| [`docs/nl-graphrag.md`](docs/nl-graphrag.md) | NL→AQL + GraphRAG evaluation harness (M5) |
| [`docs/benchmark-report.md`](docs/benchmark-report.md) | Benchmark results |

---

## License & attribution

This project builds on the **FinReflectKG** dataset published by **Domyn**:

- **Dataset:** [FinReflectKG on Hugging Face](https://huggingface.co/datasets/domyn/FinReflectKG)
- **Paper:** [arXiv:2508.17906](https://arxiv.org/abs/2508.17906)
- **Dataset license:** **CC-BY-NC-4.0 (non-commercial).** The dataset is **not redistributed** in
  this repository; the pipeline downloads it from Hugging Face. Any use of the data must honor the
  non-commercial terms and preserve **Domyn** attribution. Do not repurpose the dataset commercially.

The **code and documentation** in this repository are authored by Arthur Keen (ArangoDB). A separate
code license applies to them — see [`LICENSE`](LICENSE).

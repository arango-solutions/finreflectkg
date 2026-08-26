# FinReflectKG — Time-Travel demo visualizer

A lightweight, **local, live** demo of the FinReflectKG time-travel layer (G9/§4.8), served
against the `FinReflectKgTemporal` database. Fresh build (FastAPI + Cytoscape.js), no framework
build step.

## What it shows (v1.5)
- **DVR time-slider** — scrub 2014→2024 and the company's subgraph **crossfades** between years,
  DVR-style. The whole decade arrives in one `/api/timeline` payload; the union of all years is laid
  out **once** with stable positions, so scrubbing is pure client-side (no fetch, no relayout). The
  company node is **pinned at the centre**; facts fade in / out as they appear / disappear.
- **Depth** control (1 = direct-facts star / 2–3 = connected context). Depth ≥ 2 adds genuine
  concept↔concept edges, and the header reports how many — `depth 2 (20 context)` — because a
  company node is incident to ~99 % of its own neighbourhood, so without a reserved budget the
  star swallows every slot and the deeper views are merely denser stars. Each context edge is
  taken with the shortest path anchoring it to the company, so the view is always a *connected*
  neighbourhood — no free-floating islands.
- **Valid / Reported time toggle** — *valid* = what **held** at mid-year (`validFrom`/`validTo`);
  *reported* = what the filing **asserted** that year (`year`, transaction time). The bitemporal
  (P3) axis, made interactive.
- **Legend = type filters** — click a legend swatch to show / hide that entity type.
- **Top-N PageRank filter** (Influence panel) — keeps only entities ranked in the **corpus-wide**
  top-N at the current anchor year, *not* the top-N within this company. The global leaders are
  hubs like `net income` and `united state`, so only a fraction land in any one company's
  neighbourhood: the control reads `global PageRank top 200 — 20 of 219 here` so the survivor
  count is explicit rather than looking like a broken filter.
- **Influence over time** — top entities by GAE PageRank at the anchor year nearest the slider
  (`gae_pr_2014/2019/2020/2024`).
- **Company explorer + diffs** — year-over-year *appeared / disappeared* facts (vs 2014) and
  **backward-looking disclosures** (facts a filing asserts about periods ≥3 years earlier).

## Run
```bash
# from the repo root (connection comes from .env; DB = FinReflectKgTemporal)
.venv/bin/python -m uvicorn demo.api:app --port 8080
# then open http://localhost:8080  (try tickers: aapl, msft, amzn, … any of the 743)
```

BYOC-parity (port 8000, same entrypoint Container Manager will run):

```bash
.venv/bin/python demo/main.py
# then open http://localhost:8000
```

## Endpoints (backend)
`GET /health` · `GET /api/years` · `GET /api/tickers` · `GET /api/timeline?ticker=&depth=&clean=&axis=` (all years, one payload) ·
`GET /api/asof?ticker=&year=&limit=&depth=&clean=` · `GET /api/influence?year=&top=` ·
`GET /api/prranks?year=&top=` · `GET /api/diff?ticker=&from=&to=` · `GET /api/backward?ticker=&lag=`

## Package for Arango Container Manager (BYOC)

The demo is a FastAPI service that already serves `/` and (via `main.py`) listens on
**port 8000**, which is what [Bring Your Own Code](https://docs.arango.ai/platform-suite/container-manager/#bring-your-own-code)
requires. The archive layout matches what `py12base`'s `/scripts/entrypoint.sh`
expects: a top-level `entrypoint` file whose contents are the path
`/project/finreflectkg-demo/main.py`, the project directory, and a `the_venv/`
tree of manylinux Python 3.12 wheels so FastAPI is importable without pip
(py12base has none). Rebuild with `./scripts/package_byoc.sh` after changing
Python deps. A tarball of the project dir alone makes the platform print
`No entrypoint found, running bash instead...`.

The ETL/benchmark scripts are **not** part of this package — the graph
must already exist in the target database (typically `FinReflectKgTemporal`).

```bash
./scripts/package_byoc.sh
# writes dist/finreflectkg-demo.tar.gz
```

Then in the platform UI: **Control Panel → Container Manager → Packages**

1. Upload `dist/finreflectkg-demo.tar.gz`.
2. File name e.g. `finreflectkg-demo`, version e.g. `1.0.0`.
3. Base image **`py12base`** (Python 3.12).
4. Service URL path e.g. `finreflect`.
5. Scope it to the database that holds the graph (`FinReflectKgTemporal`).
6. Deploy.

The service is then at:

`https://<endpoint>:8529/_service/uds/_db/<db>/finreflect/`

Inside the cluster the demo uses `ARANGO_DEPLOYMENT_ENDPOINT` plus the inbound
JWT (or `ARANGO_TOKEN` if a sidecar mounts one). Asset and `/api/*` URLs are
relative so they stay under that service prefix.

## Notes
- Read-only; uses the stdlib helper `demo/arango_client.py` (local `.env` Basic
  auth, or BYOC JWT). No extra DB driver.
- Cytoscape.js is **vendored** at `demo/static/vendor/cytoscape.min.js` — fully offline, no CDN.
- The as-of canvas shows a connected neighbourhood of the company (depth 1 = a clean star), capped
  at ~140 facts for readability and always island-free. The header shows
  *shown / total · depth N (M context) · as of YEAR*.
- **Theme** — light by default, with a dark toggle in the header (persisted per device). The OS
  `prefers-color-scheme` is deliberately not consulted, so a demo on a dark-mode laptop still
  opens light. Palette is the ArangoDB one shared with the r2g Studio; the Cytoscape canvas reads
  the CSS tokens and is restyled on toggle.
- Selection is **reproducible** — both selection queries carry a deterministic `SORT e._key`.
  Without it the row order, and therefore the rendered picture, varied between runs.
- **Cleaned/Raw toggle** (header): Cleaned drops junk placeholders + skolemizes generic hubs to
  per-company bnodes (dashed green); Raw shows the graph as extracted (shared hubs + junk diamonds).

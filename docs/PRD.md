# PRD — FinReflectKG on ArangoDB (Proof of Concept)

**Status:** Draft v0.26 · 2026-09-26 (BYOC **deployed and serving on prod.demo** — G10 DEPLOYED; §4.9 corrected on three counts the August draft got wrong: the bundle is FLAT not wrapped, the base image is `py12base` not `py13base`, and the ingress forwards the mount prefix INTACT rather than stripping it)
**Authors:** Arthur Keen (ArangoDB)
**Related docs:** [data-analysis.md](data-analysis.md) · [etl-plan.md](etl-plan.md) ·
[load-report.md](load-report.md) · [sharding-analysis.md](sharding-analysis.md) ·
[multi-distribution-plan.md](multi-distribution-plan.md) ·
[schema-mapping.md](schema-mapping.md) · [cypher-queries.md](cypher-queries.md) ·
[nl-graphrag.md](nl-graphrag.md) ·
[data_dictionary.md](data_dictionary.md) · paper: [research/2508.17906v2.pdf](research/2508.17906v2.pdf)

## 0. Changelog

- **v0.26 (2026-09-26):** **BYOC deployed and verified on prod.demo**, at
  `/_service/uds/_db/FinReflectKgTemporal/finreflect/`. Getting there required correcting three
  things v0.24–v0.25 asserted and never tested against the platform: **(1)** the bundle must be a
  **flat** archive with `entrypoint` and `requirements.txt` at its root — the wrapped layout those
  versions produced belongs to the container-image contract and cannot boot as a platform package;
  **(2)** the base image is **`py12base`**, the only Python image this cluster offers, which ships
  no `uv`, so the entrypoint bootstraps pip via `ensurepip` — `py13base` is on Docker Hub but not
  on this platform; **(3)** the ingress **forwards the mount prefix intact**, so the app must strip
  it ([demo/prefix.py](../demo/prefix.py)) — the claim that envoy strips it was wrong, and the
  client-side relative-URL work is a separate, equally necessary half. The root cause of having no
  deployment at all was simpler: this repo had no `scripts/byoc_deploy.py`, while
  project-sentinel, gdelt-market-impact, agentic-graph-analytics, arango-ontoextract and
  multihop-eval all did. That script is now ported. Verified live: 743 companies, anchors
  2014/2019/2020/2024, aapl-2020 depth-1 at 125 nodes / 140 edges, msft-2024 depth-2 at 146/197,
  and all three relative assets served.
- **v0.25 (2026-08-26):** **BYOC built, deployed and live.** G10 and M9 move to
  IMPLEMENTED/DONE. `deploy/` ships both artifact shapes (container image via `build.sh`,
  ServiceMaker code package via `package.sh`) plus an operator README; five deployment paths
  verified end-to-end, including the real condition (credentials baked, **no** environment
  variables passed) and the tarball actually extracted and run inside a bare `py13base` rather
  than merely inspected. Three corrections to v0.24's account: the published prefix is
  `/_service/uds/_global/<app>/`, **not** `/_services/<name>/` (five occurrences fixed); the
  frontend URL base must derive from `location.pathname`, **not** `document.baseURI`, which
  resolves one directory too high when the service is reached without its trailing slash; and the
  JWT-pass-through paragraph is rewritten, since envoy authenticating the caller is not the
  platform injecting database credentials. Also fixes a latent defect well outside BYOC:
  `scripts/arango.py` read `.env` unconditionally at import, so the app could never run from
  environment variables alone and the credential-free image exited 1 before serving anything —
  `.env` is now optional and a missing endpoint yields a 503 naming what is absent.
- **v0.24 (2026-08-26):** **BYOC corrected against a working implementation — two of v0.23's
  claims were wrong (G10/§4.9).** `gdelt-market-impact/deploy/` already ships both paths,
  verified running against its live database, and it settles the two questions v0.23 left open
  the wrong way round. **(1) Python 3.13 is correct; the version warning is retracted.**
  `arangodb/py13base:latest` (3.13.13) is on Docker Hub and works — the public `servicemaker`
  repo is simply behind the skill. What remains true is narrower: the skill's ARM64 fallback
  cannot be followed literally (`Dockerfile.py13base` is not in the public repo) and is not
  needed. Additionally **`py12base` ships no `uv` at all**, a second reason to be on 3.13.
  **(2) The platform does NOT inject credentials** — confirmed with Emmet Allen — so the JWT
  pass-through model recorded in v0.22/v0.23 is not how a deployed service gets database access.
  A service uses what it was *built* with; `.env` is baked in, and **the artifact therefore
  becomes a secret** (gitignore `*.tar.gz`, label and gate credential-bearing images, rotate the
  password if one escapes). The JWT path still exists — the route does forward the caller's
  token — but it is a service-design choice and a data-path refactor here, not something the
  platform hands you. **(3) Six new gotchas recorded** from that implementation: arm64 images
  push silently and fail to start (build `linux/amd64`); `uv` is off `PATH` in a `RUN` layer
  (bare `exit 127`); no `pip` in the venv (use `uv pip install -c constraints.txt`); quoted
  `.env` values survive `--env-file` but not `python-dotenv`, surfacing as a misleading 401;
  `.dockerignore` large data dirs; and ServiceMaker's one-directory/one-entrypoint assumption
  breaks sibling imports. **(4) Plan of record: port `gdelt-market-impact/deploy/`** rather than
  write our own — [demo/api.py](../demo/api.py) has the identical sibling-import shape its
  `package.sh` was built to handle.
- **v0.23 (2026-08-26):** **BYOC scope corrected against the first-party packaging skill
  (G10/§4.9).** Emmet Allen's `package-for-arango-byoc-skill.md` supplied detail the derived
  account missed and changed the recommendation. **(1) The two paths have colliding names** —
  *Bring Your Own **Code*** (upload `.tar.gz`, platform builds it) vs *Bring Your Own
  **Container*** (Docker image URL); the skill documents the **Code** path, and we now take it:
  no registry to host, and it is what the first-party tooling targets. The artifact is
  `project.tar.gz` under `target/<project>/`; manual packaging is `pyproject.toml` + `main.py` +
  `tar -czf`. **(2) `uv` + `pyproject.toml` are required**, and `uv sync --extra` is
  **unsupported** — everything must live in the main `dependencies` array. The demo declares
  deps in `demo/requirements.txt`, so that is a fourth gap alongside port/entrypoint, relative
  URLs and JWT pass-through. **(3) Deploy-time choices** now recorded: Global (`_system`) vs
  database-specific scoping, `app_instance_name` for multiple instances of one version, and the
  upload metadata (file name, semantic version, service URL path). **(4) A version
  contradiction is flagged rather than resolved:** the skill and the blog both say Python
  **3.13** and the skill's ARM64 fix builds `Dockerfile.py13base`, but `servicemaker@main`
  (2026-08-24) ships only `py12base`/`py12cugraph`/`py12torch`/`node22base` and hard-codes
  `DEFAULT_PYTHON_BASE_IMAGE = "arangodb/py12base:latest"` — so that documented workaround will
  fail with *no such file*. Needs confirming with the platform team before we pin a version.
- **v0.22 (2026-08-26):** **BYOC packaging of the demo UI scoped (new G10 / §4.9).** The
  platform can host the G9-P5 visualizer as a **platform service**; the runtime contract was
  established from [arangodb/servicemaker](https://github.com/arangodb/servicemaker) (the
  packaging tool, its Helm chart and its reference service) rather than the announcement post,
  which omits it. Three findings drive the work. **(1) The container contract is small** — HTTP
  on **port 8000** at the **root path**, any image; the platform runs
  `py12base` — the only Python base image this cluster offers. It ships **no** `uv`, so the
  bundle installs from `requirements.txt` via `ensurepip`. `py13base` exists on Docker Hub
  but not on this platform. **(2) Routing forwards the prefix INTACT** — the service is
  published at `/_service/uds/_db/<db>/<instance>/` and the ingress does **not** strip the
  prefix, so BOTH halves need fixing: the browser must use relative URLs (an absolute
  `/app.js` or `/api/…` resolves to the coordinator root and 404s), AND the app must strip
  the prefix before routing. Earlier drafts of this section claimed envoy strips it; that
  was wrong, and a bundle built on it 404s on every request. **(3) Credentials are NOT injected by the platform.** Envoy authenticates the
  caller and *can* pass the JWT through, but a deployed service connects with whatever it was
  **built** with — forwarding the caller's JWT is a service-design choice, not something the
  platform does for you. Confirmed with Emmet Allen, 2026-08-26; the announcement's "handles
  authentication automatically" does not mean database credentials. This project therefore
  ships both shapes: a **credential-free** image (static UI and `/api/years` serve; any
  database endpoint returns **503** naming the missing variables) and
  `build.sh --with-env`, which bakes `.env` in so the service needs no runtime environment at
  all — at the cost of **making the image artifact a secret**. A JWT-forwarding service would
  be strictly better (no password in the image, queries respecting the caller's own
  permissions) but remains a data-path refactor: [scripts/arango.py](../scripts/arango.py)
  binds credentials at module scope and signs with Basic auth. The demo already met the
  root-path and no-CDN requirements (Cytoscape is vendored); the gaps closed were
  port/entrypoint and relative URLs. The same design
  applies to `gdelt-market-impact`'s what-if UI, which is already BYOC-shaped (port 8000, root
  path, vendored assets). Designed, not built.
- **v0.21 (2026-08-21):** **Demo v1.5 — three G9-P5 defects fixed, one of them a correction to
  v0.20's own account.** **(1) Edges rendered without nodes.** Not mark separation, as v0.20
  recorded: Cytoscape resolves same-property conflicts by *rule order*, and the `.off` rule sat
  **before** the base `edge` rule, so a hidden edge kept its `opacity: 0.75` while its node
  correctly vanished — arrowheads into empty space, in both themes. `.off` now sorts last and
  zeroes the arrow explicitly. The v1.4 counter read 0 throughout because it only tested
  `hasClass('off')` (the model, which was right) and never the resolved style (the render, which
  was wrong); it now reports **`modelOrphans`** (an edge we mean to show whose endpoint is hidden)
  and **`paintLeaks`** (an edge we mean to hide that is still painted, read from
  `e.style('opacity')`). **(2) Depth ≥ 2 returned no multi-hop edges.** The BFS was correct, but a
  company node is incident to ~99 % of its own neighbourhood (`aapl` 2021: 2,004 of 2,024 edges),
  so a flat budget slice spent every slot on the star and depth 2/3 were merely denser stars.
  Selection now budgets star and context **separately** and takes each context edge together with
  the shortest path anchoring it to the company, so the connected-component filter cannot strip it
  — depth 2/3 now yield 20 real concept↔concept edges, surfaced in the header as
  `depth N (M context)`. `/api/asof` carried a second copy of this logic and now **delegates** to
  the shared selector (32 duplicated lines removed); both selection queries gained a
  deterministic `SORT e._key`, without which row order — and so the rendered picture — varied
  between runs. **(3) The Top-N PageRank control read as broken.** It ranks **corpus-wide**, so
  "top 200" keeps only the global leaders that happen to sit in one company's neighbourhood — 20
  of 219 for `aapl` 2018. The label now says `global PageRank top N — X of Y here`. **(4)** Light
  is now the **unconditional** default; the OS `prefers-color-scheme` fallback was removed so a
  demo on a dark-mode laptop still opens light unless the presenter chose dark.
- **v0.20 (2026-08-20):** **G8 report stage wired · eval figures provider-qualified · demo v1.4
  theming.** Three accepted PRD patches. **(1) §4.7 reporting
  (`domyn_REQ-011_20260819`, obsolete):** the v0.13 claim that the NL→execute→report loop is
  "not wired here" was half wrong — the **report stage is wired** via
  [scripts/analytics_report.py](../scripts/analytics_report.py), which supplies the
  `AnalysisResult`→`ExecutionResult` adapter the package does not ship. Verified on `gae_pr_2024`:
  88 KB HTML, 3 Plotly charts, 3 insights, 3 recommendations. Two causes had hidden the whole
  layer: no adapter, and plotly absent so charts degraded through a silent optional import.
  Only the **autonomous chaining** remains pending. **(2) §4.6 provider attribution
  (`domyn_REQ-006_20260813`, clarification):** LLM-dependent scores are now published **with the
  provider and model that produced them**. GraphRAG answer synthesis is **4/5 (`openai/gpt-4o`)**,
  not 5/5 — the 5/5 was `anthropic/claude-sonnet-4-5` and is not reproducible since that key was
  revoked. Not a code regression: retrieval and grounding are unchanged (60 facts, all grounded);
  the one failure is a false abstention on the CINF stake question. NL→Cypher 19/22 · 9/22 is
  `openai/gpt-4o-mini` and stands. **(3) §4.8 G9-P5 demo v1.4 (`domyn_G9-P5_theme_20260819`,
  clarification):** the **ArangoDB brand palette and light/dark theme contract are now shared with
  the r2g Studio** (light default, `data-theme` opt-in, pre-paint resolution, persisted choice).
  Because Cytoscape bakes its stylesheet at construction, the canvas reads the CSS tokens and is
  re-styled on toggle. Node marks gained a surface-coloured ring and a raised minimum size so they
  read against edges, arrowheads and labels in both themes. *(Corrected in v0.21: this entry
  originally credited a dangling-edge counter with diagnosing a "missing nodes" report as mark
  separation. That was wrong — the counter read 0 because it inspected class state rather than
  resolved style, and the real cause was stylesheet rule ordering.)*
- **v0.19 (2026-08-16):** **Demo v1.3 — DVR timeline + bitemporal/PageRank interactivity (G9-P5).**
  The as-of view now renders a **connected neighbourhood** of the company (depth 1 = direct-facts
  star; a **Depth** control expands to 2–3 hops), with the company node **pinned at the centre** and
  the decade scrubbable **DVR-style** (one `/api/timeline` payload, union laid out once, slider
  crossfades between years — no per-year relayout). Adds a **valid/reported** bitemporal-axis toggle
  (valid-time vs the filing's transaction-time — P3 made interactive), a **legend that doubles as
  type filters**, and a **Top-N PageRank** filter (`/api/prranks`) that restricts the view to the
  most globally-influential entities. Connected-component filtering guarantees no concept↔concept
  islands. Applies accepted patch `domyn_G9-P5_clarify_20260816`.
- **v0.18 (2026-08-15):** **Interactive time-travel demo visualizer (G9/§4.8 — P5).** The
  time-travel layer now has a dedicated, local, live demo UI ([demo/](../demo/), FastAPI +
  vendored Cytoscape.js, read-only vs `FinReflectKgTemporal`): a time-slider as-of view,
  an influence-over-time panel (GAE PageRank per anchor year), a company explorer with
  year-over-year appeared/disappeared diffs + backward-looking disclosures, and a
  **Cleaned/Raw toggle** that shows the generic-mention cleanup (junk dropped + generic hubs
  skolemized to per-company bnodes) side-by-side with the raw extraction. Deliverables:
  [demo/api.py](../demo/api.py), `demo/static/*`, [demo/screenshot.sh](../demo/screenshot.sh).
  Documented as §4.8 sub-capability P5 (was code-ahead-of-PRD; promoted via /prd-sync patch
  `domyn_G9-P5_20260815`).
- **v0.17 (2026-08-13):** **P4 PageRank-per-year on comparable cleaned snapshots.** The first
  GAE run reused cached `gae_pr_*` collections without checking the snapshot they came from,
  so 2019 was ranked off an 8.5%-complete snapshot (166,935 vs 1.96 M edges) and 2024 off
  un-rewired topology — plus a junk placeholder `default` ranked #1/#2. Fix:
  [scripts/temporal_pagerank.py](../scripts/temporal_pagerank.py) now validates the snapshot
  *before* resume-skip, refuses partial materialization, drops junk-placeholder edges, and
  `--rebuild`/`--recompute` force a consistent re-run. Live `FinReflectKgTemporal`: snapshots
  match junk-excluded as-of counts (2014: 1,142,019 · 2019: 1,963,246 · 2020: 2,131,464 ·
  2024: 2,138,110); `default` gone from the top-15; `net income` #1 in every year.
- **v0.16 (2026-08-10):** **Bitemporal + temporal analytics on the time-travel layer (G9/§4.8 — P3, P4).**
  P3: filing `year` as transaction-time vs `validFrom`/`validTo` valid-time → a backward-looking
  restatement report (1.82 M edges, 10.5 %) + "as-known-as-of" ([scripts/restatements.py](../scripts/restatements.py)).
  P4: per-as-of-year centrality + topic-shift trend analytics ([scripts/temporal_analytics.py](../scripts/temporal_analytics.py))
  and GAE PageRank-per-year ([scripts/temporal_pagerank.py](../scripts/temporal_pagerank.py)).
- **v0.15 (2026-08-08):** **Time-travel layer built + validated (G9/§4.8 — Done, M8).**
  Built `FinReflectKgTemporal` (OneShard) via [scripts/build_temporal.sh](../scripts/build_temporal.sh):
  augmented all **17,513,372** relations edges with numeric `validFrom`/`validTo`, created the MDI +
  composite `validFrom` VCIs + named graph. **Validation green**
  ([scripts/validate_temporal.py](../scripts/validate_temporal.py)): counts reconcile, 0 edges missing
  temporal fields, **as-of query is MDI-backed** (confirmed via `explain`), AAPL `operates_in` as-of =
  48 (2014) / 76 (2018) / 85 (2024). **Data-quality fix:** ~654 K edges had OCR-noisy start years
  (e.g. 1163 / 8176) that parse cleanly but would pollute snapshots — `validFrom` is clamped to the
  filing year when the parsed start is outside [2013, 2026] (`endDate` left lenient for real
  far-future maturities); 108,914 degenerate spans repaired. Added a `finreflectkg-temporal-mcp`
  convenience MCP entry (default DB `FinReflectKgTemporal`).
- **v0.14 (2026-08-07):** **Time-travel layer scoped + P0-verified (G9/§4.8, M8).**
  10 fiscal years of 10-Ks ⇒ point-in-time reconstruction. Design: numeric valid-time
  `validFrom`/`validTo` (`YYYYMM` ints, `NEVER_EXPIRES=999912`) **directly on `relations`**
  (a derived `fact_relations` overlay was proposed and **dropped as unnecessary**) + an
  **MDI** index; adapts the `network-asset-management-demo` "TTL" blueprint to this
  read-only LPG. **`explain` spike on the live 3.12 cluster:** a direct-edge as-of
  (`validFrom <= t AND validTo > t`) **uses the MDI** (filter fully index-covered); a
  node-anchored typed as-of uses a **persistent composite index** `(_from, type, validFrom)`,
  not the MDI; a `p.edges[*] ALL` **traversal does NOT engage the MDI** (edge-index +
  per-edge post-filter — same as the VCIs, §4.2). ⇒ as-of is expressed as **direct edge
  queries**; multi-hop temporal uses `PRUNE`+filter. Target DB **`FinReflectKgTemporal`
  (OneShard)**. Details: §4.8.
- **v0.13 (2026-07-30):** **Agentic planning pipeline completes end-to-end (G8 top
  layer).** Fixed two upstream bugs in `agentic-graph-analytics` (`graph_analytics_ai`):
  (1) `state.py`/report `json.dump` lacked `default=str` (enum not serializable), and
  (2) `steps.py` referenced `ExtractedRequirements.all_requirements` (the attribute is
  `requirements`). `WorkflowOrchestrator.run_complete_workflow` now **COMPLETES all 7
  steps in ~23 s** — NL requirements → schema analysis → **10 GAE use cases mapped to
  algorithms** (PageRank, WCC, label_propagation, betweenness, scc); artifacts in
  `data/analytics_agentic/`. **Scope clarified:** this orchestrator is the **planning**
  layer (its steps end at `save_outputs`/use-cases); GAE **execution** is the
  deterministic base ([scripts/analytics.py](../scripts/analytics.py), verified) that the
  plan's algorithms feed into. The fully-autonomous NL→execute→report loop is a separate
  mode of the tool (`graph_analytics_ai/ai/agents/`), not wired here — **superseded in
  v0.20: the report stage was wired ([scripts/analytics_report.py](../scripts/analytics_report.py));
  only the autonomous chaining remains unwired.** *(Also fixed this
  repo's PRD-drift gate: `drift_queue.py` was queuing cross-repo edits — now scoped to
  files inside this repo, excluding `.claude/`; `drift_stop_gate.sh` PRD-count `0\n0`
  glitch cleaned. `.claude/` is gitignored so those are local-only.)*
- **v0.12 (2026-07-29):** **Agentic NL→insights front-end verified; full auto-execution
  blocked by an upstream bug (G8, top layer).** Ran `agentic-graph-analytics`'s
  `WorkflowOrchestrator.run_complete_workflow` ([scripts/analytics_agentic.py](../scripts/analytics_agentic.py))
  over a business-requirements doc ([analytics-requirements.md](analytics-requirements.md)),
  LLM via OpenRouter (default, `OPENROUTER_API_KEY`, no extra SDK). It completed 6 steps —
  parse → extract requirements (conf 0.90) → extract/analyze schema → generate PRD →
  **generate 10 graph-analytics use cases** correctly mapped to GAE algorithms (PageRank
  centrality, WCC connectivity, label_propagation communities, betweenness bridges, scc)
  and even predicted "net income, revenue … surfaced" (matching the base PageRank result).
  Artifacts written: `data/analytics_agentic/{product_requirements,use_cases,schema_analysis}.md`.
  The run then **FAILED before GAE auto-execution** on a one-line serialization bug in the
  tool: `graph_analytics_ai/ai/workflow/state.py:220` `json.dump(self.to_dict(), …)` has no
  enum handler, so the `DocumentType`/`UseCaseType` enum isn't JSON-serializable
  (`default=str` fixes it). Bug is upstream in `agentic-graph-analytics` (v3.0). Base GAE
  execution is already proven, so the agentic layer would produce the same results once
  the tool bug is fixed.
- **v0.11 (2026-07-29):** **Graph-analytics base layer implemented & verified (G8).**
  Resumed via **`agentic-graph-analytics`** (`import graph_analytics_ai`, ACP-ready)
  installed into `.venv311`; re-pointed [scripts/analytics.py](../scripts/analytics.py)
  and ran GAE jobs **end-to-end** on the self-managed ACP engine (deploy → readiness →
  load → analyze → store → cleanup): **PageRank** — top nodes `net income`, `revenue`,
  `net sale`, `operate income`, … (the central `FIN_METRIC` supernodes), ~1.9 min,
  3,099,773 result docs, ≈$0.013 — and **WCC** — 3,322 components, one giant component of
  3,091,396 nodes (99.7%), ~1.5 min. Results land in non-mutating `gae_<algorithm>`
  collections. The GRAL ingress-readiness issue that blocked the standalone orchestrator
  is handled by this client (readiness poll + transient-404 retry). Agentic NL→insights
  layer still pending. G8/M7 → Partial.
- **v0.10 (2026-07-29):** **Graph analytics (GAE) — goal added, availability + approach
  established, implementation deferred (new G8 / §4.7).** Confirmed the ArangoDB Graph
  Analytics Engine is available on this deployment: it's an **ArangoDB Platform (ACP)**
  cluster and a GAE engine **deploys/deletes cleanly** (self-managed, `/gen-ai/v1/graphanalytics`
  lifecycle). Root-caused a compute-load failure: the per-engine route
  (`/gral/<id>/v1/loaddata`) is only live ~30–60 s after deploy while the GRAL ingress
  rolls out; the standalone **`graph-analytics-orchestrator`** retries only ~3×/~12 s (by
  re-deploying) and 404s, whereas **`agentic-graph-analytics`** (`graph_analytics_ai`) is
  ACP-ready (readiness polling + retry on the transient `unknown path '/gral/..'`) and
  ships **both** a deterministic orchestrator mode and an agentic NL→insights mode.
  **Decision:** integrate via **`agentic-graph-analytics`** (both layers — it contains
  the deterministic orchestrator *and* the agentic layer), not the standalone
  orchestrator. A draft scaffold ([scripts/analytics.py](../scripts/analytics.py)) exists,
  to be re-pointed. No further cluster work this pass.
- **v0.9 (2026-07-22):** **M5 complete — NL→Cypher front-end + GraphRAG synthesis.**
  Repaired `.venv311` (installed the newly-extracted `arango-query-core` dependency)
  and ran the schema-aware **NL→Cypher front-end**
  ([scripts/nl2cypher_eval.py](../scripts/nl2cypher_eval.py)): **19/22 transpile,
  9/22 execute** with **0 `MAPPING_NOT_FOUND`** — the vocabulary gap that capped the
  hand-written path disappears when the model writes in the ontology's own labels
  (CINF-stake queries **0 → 219 rows**). **GraphRAG answer synthesis** scored **5/5
  on `anthropic/claude-sonnet-4-5`** at the time
  ([scripts/graphrag_rubric.py](../scripts/graphrag_rubric.py)), including
  a faithful abstention on an out-of-scope question and catching an inverted-premise
  question. **Superseded — see §4.6 "LLM-dependent figures are provider-scoped":**
  that key was later revoked and the current configured provider scores **4/5**. **Root-caused the gold-set vocabulary mismatch against live data:** the
  gold Cypher was authored against a **sibling schema** (`:RISK` vs this graph's
  `RISK_FACTOR`); `ORG_REG` is real in FinReflectKG (11,193 nodes) but dropped by the
  analyzer's **top-20 entity cap**; `:METADATA` is genuinely absent. Direct
  hand-written Cypher holds at **14/22 · 7/22**
  ([scripts/cypher_eval.py](../scripts/cypher_eval.py)). Remaining ceiling is upstream
  (transpiler ERR 1511 on multi-`WITH`; **non-VCI AQL efficiency**; analyzer entity cap;
  `reduce()`), not a FinReflectKG concern. Corrected the stale "awaits a provider key"
  notes (a key is configured). Details: [nl-graphrag.md](nl-graphrag.md).
- **v0.8 (2026-07-07):** **Upstream vocabulary fix verified.** After the `arango-cypher-py`
  resolver was made case/normalization-insensitive, the Cypher→AQL retest went
  **3/22 → 14/22 transpile (7/22 execute)**. Updated the bug report with the retest and two
  newly-pinpointed upstream transpile-correctness bugs (invalid AQL: `collection not found: loc`;
  `variable 'v' assigned multiple times`), plus that `reduce()` still errors in the installed tree
  and the `ORG_REG` entity-cap remains (analyzer). Added a `request_timeout` to the eval harness.
- **v0.7 (2026-07-07):** **Built the `arango-cypher-py` integration**
  ([scripts/cypher_eval.py](../scripts/cypher_eval.py), in a dedicated py3.11 `.venv311`):
  acquires a live `MappingBundle` (20 entities / 200 relationship types) and transpiles
  the gold-set Cypher. **3/22 transpile+execute as-is;** the rest expose a
  schema-vocabulary gap — the gold Cypher uses source Neo4j spellings (`Has_Stake_In`,
  `FIN_METRIC`) while the mapping exposes the graph's lemmatized/normalized labels
  (`has_stake_in`, `FINMETRIC`), plus one transpiler gap (`reduce()`). Removed the
  bespoke `scripts/nl2aql.py`. **Determined the 19 failures are an upstream
  `arango-cypher-py` vocabulary-resolution gap** (exact-match `MappingResolver` + lossy
  label normalization + top-N entity cap), **not** a FinReflectKG concern — filed a bug
  report/feature request at `arango-cypher-py/docs/finreflectkg-cypher-vocabulary-bug-report.md`.
  FinReflectKG will not rewrite its gold Cypher; the fix is upstream and/or via the
  schema-aware `nl2cypher` front-end.
- **v0.6 (2026-07-07):** **Recorded the `arango-cypher-py` requirement (new §4.6).**
  The NL/Cypher query layer for G6/M5 must use
  [`arango-cypher-py`](https://github.com/arango-solutions/arango-cypher-py) (the
  arango-solutions Cypher→AQL transpiler + `nl2cypher`), with FinReflectKG as a real
  workload for it — this was an implicit requirement missing from the PRD. The
  bespoke `scripts/nl2aql.py` from v0.5 is **superseded** by that integration (still
  pending); GraphRAG retrieval/grounding stands. Corrected the §4.4 note:
  `arango_cypher_schema_cache` is that library's schema cache, not unrelated tooling.
  G6 downgraded Done→Partial accordingly.
- **v0.5 (2026-07-07):** **NL-query harness + GraphRAG pipelines (G6 done, M5 in
  progress).** Added a gold-set runner ([nl-graphrag.md](nl-graphrag.md)) that parses
  the 22 curated queries from [cypher-queries.md](cypher-queries.md) (21/22 execute),
  a pluggable LLM helper, an NL→AQL translator (live-schema + few-shot prompt), and a
  GraphRAG pipeline (name-index entity linking → VCI neighborhood → `chunks`
  grounding). Verified grounded retrieval on `FinReflectKgSmart` (24/24 facts carry
  co-located source text). LLM-dependent generation/answer scoring awaits a provider key.
- **v0.4 (2026-07-05):** **Cross-distribution benchmarks complete (G5/M4 done).**
  Ran the PRD §6 suite against all three distributions with deterministic
  scanned-edge + explain-locality metrics ([benchmark-report.md](benchmark-report.md)).
  Headline: Design 2's per-company concept duplication **decomposes the `net income`
  supernode ~250×** (228.6 ms → 0.9 ms; 59,315 → 35 scanned edges) for company-scoped
  queries, at the predicted cost of costlier global concept roll-ups (name lookup
  returns 873 per-company copies; cross-company 2-hop pays `RemoteNode` hops).
- **v0.3 (2026-07-05):** **SmartGraph build complete.** `FinReflectKgSmart`
  (Design 2, Disjoint SmartGraph by `ticker`) loaded & validated —
  **6,658,668 nodes / 17,513,372 edges / 1,384,513 chunks**, VCIs built,
  referential integrity clean, and a per-company traversal confirmed
  **shard-local** (no `RemoteNode`) with its source text co-located. All three
  distributions (baseline, OneShard, SmartGraph) are now built (G7/M6 done). The
  interim `FinReflectKgSmartPilot` pilot database was retired.
- **v0.2 (2026-06-29):** Full dataset loaded & validated (M3 done); corrected the
  VCI finding (VCIs accelerate **direct edge-collection queries, not pattern
  traversals** on 3.12.x cluster — see [load-report.md](load-report.md)); added the
  **multi-distribution** requirement (OneShard + SmartGraph builds, G7/§4.5) after
  performance-testing requirements changed; corrected loaded chunk count.
  **SmartGraph design locked to Design 2** (Disjoint
  SmartGraph by `ticker`, concepts duplicated, `chunks` co-located by `ticker`).
- **v0.1 (2026-06-12):** Initial POC scope.

## 1. Background

Domyn publishes [FinReflectKG](https://huggingface.co/datasets/domyn/FinReflectKG), a
financial knowledge graph extracted from S&P 500 10-K SEC filings (2014–2024):
**17.51 M triples** over **743 companies**, with entity/target types, normalized
relationship names, temporal validity bounds, and the full source-text chunk for
every triple (paper: [arXiv:2508.17906](https://arxiv.org/abs/2508.17906)).

This is a POC to load that dataset into a managed ArangoDB deployment and evaluate:

1. **Graph query performance** — typed traversals at scale, supported by
   vertex-centric indexes (VCI).
2. **Natural-language query performance** — NL → AQL / GraphRAG-style question
   answering over the graph, leveraging the per-triple source text.

## 2. Goals

| # | Goal | Success criterion | Status |
|---|------|-------------------|--------|
| G1 | Full dataset loaded into the remote ArangoDB instance defined in `.env` (db `FinReflectKG`) | Row counts in ArangoDB reconcile exactly with the source parquet (nodes, relations, chunks) | **Done** — loaded & validated, 0 errors ([load-report.md](load-report.md)) |
| G2 | LPG data model with Neo4j-aligned terminology | One `Node` document collection, one `relations` edge collection; edges carry `type`, `_fromType`, `_toType` | **Done** |
| G3 | Vertex-centric indexes on edges | Persistent indexes on `(_from, type, _toType)` and `(_to, type, _fromType)`; AQL profiles show index use on **direct edge-collection queries** (see §4.2 note) | **Done** (with refined finding) |
| G4 | Repeatable, resumable ETL | Pipeline re-runnable end-to-end; idempotent (deterministic `_key`s, `onDuplicate` handling); single command per stage | **Done** — `scripts/rebuild_all.sh` |
| G5 | Query-performance baseline | A benchmark suite of representative graph queries with recorded latencies (see §6) | **Done** — suite ([scripts/benchmark.py](../scripts/benchmark.py)) run across all three distributions; deterministic scanned-edge + explain-locality metrics recorded ([benchmark-report.md](benchmark-report.md)) |
| G6 | NL-query readiness | Source-text chunks joinable from every edge; **Cypher→AQL / NL→Cypher via `arango-cypher-py`** (§4.6) + GraphRAG grounding | **Done (FinReflectKG-side)** — NL→Cypher **front-end** run ([scripts/nl2cypher_eval.py](../scripts/nl2cypher_eval.py)): **19/22 transpile, 9/22 execute, 0 `MAPPING_NOT_FOUND`** (vocabulary gap closed); hand-written Cypher path 14/22 · 7/22 ([scripts/cypher_eval.py](../scripts/cypher_eval.py)); GraphRAG grounding 24/24 + **answer synthesis 4/5 (`openai/gpt-4o`, 2026-08-13; was 5/5 on `anthropic/claude-sonnet-4-5`, no longer reproducible)** ([scripts/graphrag.py](../scripts/graphrag.py), [scripts/graphrag_rubric.py](../scripts/graphrag_rubric.py)); gold-set AQL runner 21/22. Remaining ceiling is upstream (transpiler bugs, non-VCI AQL efficiency, analyzer cap) — see [nl-graphrag.md](nl-graphrag.md) |
| G7 | Multiple distributions for comparative scale benchmarking | Same dataset built as a **OneShard** db (`FinReflectKgOneShard`) and a **sharded SmartGraph** db (`FinReflectKgSmart`) alongside the baseline `FinReflectKG`; sharding verified (see §4.5) | **Done** — OneShard and SmartGraph both built & verified ([multi-distribution-plan.md](multi-distribution-plan.md)) |
| G8 | Graph analytics over the graph (GAE): centrality/PageRank, connected components (WCC/SCC), community detection — deterministic jobs + an agentic NL→insights layer | Reproducible GAE jobs on `Node`/`relations` with recorded results (non-mutating result collections), plus an NL/requirements→insights flow (see §4.7) | **Partial** — deterministic base **verified** ([scripts/analytics.py](../scripts/analytics.py)): PageRank + WCC end-to-end on all 3.1 M nodes (self-managed ACP GAE); agentic **planning** layer **completes** ([scripts/analytics_agentic.py](../scripts/analytics_agentic.py)): NL requirements → 10 GAE use cases. Remaining (optional): the fully-autonomous NL→execute→report loop |
| G9 | **Time-travel (temporal) queries** — point-in-time as-of, current-state, and year-over-year diff over the 10 fiscal years | Numeric `validFrom`/`validTo` on `relations` + an MDI temporal index; as-of / current / diff queries return correct rows and are index-backed (MDI for unbounded, persistent composite for node-anchored — verified §4.8); built in `FinReflectKgTemporal` | **Done** — `FinReflectKgTemporal` (OneShard) built & validated: 17.51 M edges carry `validFrom`/`validTo`, as-of is MDI-backed (verified via `explain`), AAPL `operates_in` as-of 48/76/85 (2014/18/24) ([build_temporal.sh](../scripts/build_temporal.sh), [validate_temporal.py](../scripts/validate_temporal.py)) |
| G10 | **BYOC packaging of the demo UI** — run the G9-P5 visualizer as an ArangoDB platform service rather than on a laptop | A flat ServiceMaker bundle on `py12base`, mounted at `/_service/uds/_db/<db>/<instance>/`, with the prefix stripped server-side and relative URLs client-side | **DEPLOYED & VERIFIED** 2026-09-26 — live at `/_service/uds/_db/FinReflectKgTemporal/finreflect/` (service `arango-user-defined-iu37r`, v1.0.0-1). [deploy/entrypoint](../deploy/entrypoint), [deploy/package.sh](../deploy/package.sh), [scripts/byoc_deploy.py](../scripts/byoc_deploy.py), [demo/prefix.py](../demo/prefix.py). See §4.9 |

### Non-goals (this phase)

- Entity resolution / deduplication beyond what the dataset already provides
  (e.g. merging `united state` with `united states of america`).
- Embedding generation and vector search over `chunk_text` (natural phase 2;
  the model leaves room for it).
- A production-grade application UI.
- Benchmarking against Neo4j or other engines (model is kept Neo4j-comparable
  so this remains possible later).

## 3. Users & stakeholders

- **ArangoDB (Arthur Keen)** — builds and runs the ETL, designs the model and
  indexes, runs benchmarks.
- **OneShard performance testing** — the `FinReflectKgOneShard` build.
- **Community / cluster graph** — the sharded SmartGraph build (`FinReflectKgSmart`).
- **Domyn** — publisher of the FinReflectKG dataset (CC-BY-NC); credited as the data
  source.

## 4. Requirements

### 4.1 Data model (LPG, Neo4j terminology)

The schema defines **24 canonical entity types** and **~30 canonical
relationship types** (see [data_dictionary.md](data_dictionary.md)), but the
extraction pipeline emitted a long tail of non-canonical relationship strings —
**30,535 distinct values across the full dataset**, 96.6% of which occur fewer
than 100 times (measured; see [data-analysis.md](data-analysis.md) §2). Mapping node
types → document collections and relationship types → edge collections is
unworkable at that cardinality, so the model is a **labeled property graph**
with a single node collection and a single edge collection, mirroring Neo4j's
node/relationship vocabulary:

- **`Node`** (document collection) — one document per distinct
  `(name, type)` pair across entity and target columns.
  - `_key`: deterministic hash of `name|type` (raw names contain `/`, spaces,
    and other characters illegal in ArangoDB keys; 91% of sampled rows have at
    least one such character).
  - `name` (string, normalized as in the dataset), `type` (e.g. `ORG`,
    `FIN_METRIC`, `GPE`).
- **`relations`** (edge collection) — one edge per source row (triple
  occurrence), preserving provenance and temporal bounds rather than
  collapsing duplicates.
  - `_key`: the dataset's `triplet_id` (key-safe, globally unique) → re-imports
    are idempotent.
  - `_from`, `_to`: refs into `Node`.
  - `type`: relationship name (e.g. `discloses`, `operates_in`).
  - `_fromType`, `_toType`: copies of the source/target node types, enabling
    vertex-centric indexes that prune traversals by edge type **and** the type
    of the node at the far end.
  - Temporal & provenance properties: `startDate`, `endDate` (parsed to
    sortable form where possible), `extractionType`, `ticker`, `year`,
    `sourceFile`, `pageId`, `chunkKey`.
- **`chunks`** (document collection) — deduplicated source-text chunks.
  - `_key`: deterministic hash of `(ticker, year, page_id, chunk_id)`.
  - `ticker`, `year`, `pageId`, `chunkId`, `text`.
  - Rationale: `chunk_text` averages ~2.9 KB and is repeated for every triple
    extracted from the same chunk (≈ 12× in sampling). Inlining it on edges
    would store ~50 GB of text; deduplicating stores ~4–5 GB and keeps edges
    small, which matters for traversal performance. Edges reference chunks via
    `chunkKey` (1-hop join when NL/GraphRAG needs source text).

### 4.2 Indexing

- VCI 1: persistent index on `relations(_from, type, _toType)`.
- VCI 2: persistent index on `relations(_to, type, _fromType)`.
- Persistent index on `Node(name)` (exact lookup by entity name; entry point
  for NL queries) and `Node(type)`.
- Optional (benchmark-driven): `relations(ticker, year)` for temporal/company
  slicing.
- **Label-rooted access path (added 2026-07-22, M5/G6):** persistent indexes
  `relations(type, _fromType, _toType)` (`vci_type_fromtype_totype`) and
  `relations(type, _toType, _fromType)` (`vci_type_totype_fromtype`). The two VCIs
  above are **node-anchored** (leading `_from`/`_to`), so **label-wide** aggregations
  ("all `:ORG` operating in > N `:GPE`" — no bound start node) engage no index and scan
  the full edge collection. These `type`-leading indexes prune such filters to the
  matching slice — e.g. `operates_in`/ORG/GPE = 313,407 of 17.5 M edges (1.79%): the
  direct-edge form's estimated cost drops **119,966,595 → 465** and it runs ~1.9 s vs.
  timing out at the 90 s cap. As with the VCIs, only **direct edge-collection queries**
  use them (pattern traversals do not — see the note below); the `arango-cypher-py`
  transpiler must emit direct-edge single-hop AQL to benefit (filed upstream —
  [nl-graphrag.md](nl-graphrag.md) §Pending, and
  `arango-cypher-py/docs/finreflectkg-aql-codegen-and-access-path-report.md`).
- Indexes are created **after** bulk load (faster than maintaining them during
  import).

> **Verified finding (load-report.md):** on the ArangoDB 3.12.x cluster, the VCIs
> are used by **direct edge-collection queries** —
> `FOR e IN relations FILTER e._from == @x AND e.type == … AND e._toType == …` —
> which narrow perfectly (e.g. the `net income` supernode scans only the 59,315
> matching edges). **Pattern traversals** (`FOR v,e IN 1..1 OUTBOUND … relations`)
> do **not** pick up the VCIs here; the optimizer uses the built-in `edge` index
> and applies `type`/`_fromType` as post-filters (an explicit `indexHint` with
> `forceIndexHint:true` did not change this). **Implication:** write 1-hop typed
> neighborhood queries as direct edge-collection queries; reserve pattern
> traversals for variable-depth pathfinding.

### 4.3 ETL

- **Download**: all 103 parquet shards (~1.7 GB) from Hugging Face.
- **Preprocess**: DuckDB-based transform to JSONL (`Node`, `relations`,
  `chunks`), including key hashing, type copying onto edges, and chunk
  dedup. No full-dataset in-memory load (the dataset is ~50 GB decompressed).
- **Import**: `arangoimport` from an `arangodb` CE Docker image (client tools
  only) against the remote endpoint, JSONL input, parallel threads.
  The Rust toolset (`~/code/arango-data-tools-rs`, `arangox`) was evaluated:
  its import library is complete but the CLI is not yet wired, and it lacks
  parquet support and collection/index creation, so `arangoimport` is the
  primary path for this POC. Revisit `arangox` once its CLI lands (this POC is
  a good first real workload for it).
- **Validate**: count reconciliation + spot-check traversals.

Full detail: [etl-plan.md](etl-plan.md).

### 4.4 Environment & constraints

- **Target**: remote ArangoDB **3.12.x Enterprise** cluster (3 Coordinators / 3
  DBServers / 3 Agents; `ARANGO_ENDPOINT` in `.env`). Enterprise is **required** —
  OneShard, SmartGraph, and SatelliteCollections (§4.5) are Enterprise features.
- **Databases** on the endpoint (one dataset, three distributions — see §4.5):
  - `FinReflectKG` — baseline, loaded & validated. (Note: this is a single-shard
    **flexible** db, *not* a true OneShard db, despite earlier informal labelling.)
  - `FinReflectKgOneShard` — OneShard db, built & verified.
  - `FinReflectKgSmart` — Disjoint SmartGraph db (Design 2), built & verified.
  - `arango_cypher_schema_cache` on the endpoint is **not unrelated** — it is the
    schema cache of **`arango-cypher-py`**, the Cypher→AQL / NL→Cypher engine this
    POC's query layer is required to use (see §4.6). The `aga_*` and `benchmark_*`
    collections are unrelated app tooling; the POC builds keep to their own
    databases and the named graph manifest to avoid those.
- **Secrets** stay in `.env` (gitignored); never in code or docs.
- **License**: dataset is **CC-BY-NC-4.0** (non-commercial). Fine for this
  research/POC use; flag to both parties before any commercial repurposing.
- Local workstation: macOS, Docker available; Python venv at `.venv` with
  DuckDB for preprocessing. All 103 source parquet shards + the staging JSONL are
  cached locally, so rebuilds import one-way without re-downloading.

### 4.5 Multi-distribution builds (G7)

Performance-testing requirements changed: the same dataset must exist under
multiple distributions so OneShard, single-server, and cluster-scale SmartGraph
behaviour can be benchmarked head-to-head. The data model (§4.1) and indexes
(§4.2) are identical across all three; only **placement** differs. The pipeline
scripts are parameterized (per-build `ARANGO_DB`/sharding/graph via env) so one
canonical pipeline drives all three. Full design: [multi-distribution-plan.md](multi-distribution-plan.md).

| DB | Distribution | Owner / use | Status |
|---|---|---|---|
| `FinReflectKG` | flexible db, 1 shard/collection (not OneShard) | baseline / NL-query work | loaded |
| `FinReflectKgOneShard` | **OneShard** db (`sharding: "single"`, all collections `distributeShardsLike` `_graphs`, co-located on one DBServer) | OneShard performance testing | **built & verified** (`scripts/build_oneshard.sh`) |
| `FinReflectKgSmart` | **Disjoint SmartGraph** (smart key `ticker`; shared concepts duplicated per company; `chunks` smart-sharded by `ticker` for text co-location) | text-to-graph / cluster graph | **built & verified** (`scripts/build_smart.sh`; 6.66 M nodes / 17.51 M edges, shard-local traversals confirmed) |

**Constraints & decisions:**
- OneShard's `sharding: "single"` can only be set at **database creation**, so each
  distribution is a separate database (cannot be toggled in place).
- The 17.5 M-edge graph is a near-perfect SmartGraph candidate: **0.00% cross-company
  references** (a disjoint union of 743 per-company subgraphs), so the smart key is
  `ticker`. The shared concept layer (17% of nodes; 27.7% concept→concept edges that
  break the naive smart+satellite design) is handled by **Design 2 (locked 2026-06-29):
  duplicate shared concepts per company** — keeps the single `relations` model + VCI
  fast path, naturally decomposes supernodes, ~2.1× nodes (edges not duplicated).
  The requirement is simply a SmartGraph (the text-to-graph tooling needs one) with
  **text co-located with related entities**, so `chunks` is **smart-sharded by `ticker`**
  too (a company's source text lands on its subgraph's shard). Satellites (Design B)
  were considered and rejected — not needed and they'd fragment `relations`. See
  [multi-distribution-plan.md](multi-distribution-plan.md) §5 (incl. §5.7 monitoring).
- OneShard collections inherit `replicationFactor=2` from the `_graphs` leader (vs.
  the baseline's RF1) — immaterial to read-traversal benchmarks, relevant to write/HA.

### 4.6 NL / Cypher query layer (G6, M5)

The natural-language and Cypher query layer **must use
[`arango-cypher-py`](https://github.com/arango-solutions/arango-cypher-py)** — the
arango-solutions Python-native **Cypher→AQL transpiler** (with an `nl2cypher`
module and a schema cache/acquisition layer) — rather than a bespoke NL→AQL
translator. FinReflectKG is a **real workload** for that library (analogous to the
`arangox` framing in §4.3), and the two projects share this cluster: the
`arango_cypher_schema_cache` collection (§4.4) is `arango-cypher-py`'s own schema
cache.

- **Pipeline:** NL →(`arango_cypher.nl2cypher`)→ Cypher →(`arango_cypher.translate`,
  with a `MappingBundle` acquired from the target db)→ AQL → execute. The public API
  is `arango_cypher.translate(cypher, mapping=…) -> TranspiledQuery(aql, bind_vars, …)`
  and `arango_cypher.execute(cypher, db=…, mapping=…)`.
- **Gold set:** the 22 curated NL/**Cypher**/AQL triplets in
  [cypher-queries.md](cypher-queries.md) are the evaluation corpus — the Cypher
  column is transpiled by `arango-cypher-py` and the output compared to (and executed
  alongside) the reference AQL.
- **Scope note:** the bespoke `scripts/nl2aql.py` from the first M5 pass is
  **superseded** by an `arango-cypher-py` integration; the GraphRAG retrieval +
  chunk-grounding pipeline (`scripts/graphrag.py`) remains valid and orthogonal.
- Details & status: [nl-graphrag.md](nl-graphrag.md).

**LLM-dependent figures are provider-scoped.** This layer is deliberately
provider-agnostic — the provider is chosen by `LLM_PROVIDER` with a key-based fallback
([scripts/llm.py](../scripts/llm.py), [scripts/nl2cypher_eval.py](../scripts/nl2cypher_eval.py)) —
so **every evaluation score below is only meaningful together with the provider and model
that produced it**, and must be re-measured when `LLM_PROVIDER` changes. Current figures:

| figure | provider / model | reproducible |
|---|---|---|
| NL→Cypher 19/22 transpile · 9/22 execute · 0 `MAPPING_NOT_FOUND` | `openai/gpt-4o-mini` | yes |
| GraphRAG grounding 24/24 (59–60 of 60 facts carry source text) | n/a — retrieval only | yes |
| GraphRAG answer synthesis **4/5** | `openai/gpt-4o` (2026-08-13) | yes |
| GraphRAG answer synthesis 5/5 | `anthropic/claude-sonnet-4-5` | **no — key revoked** |

The 5/5 → 4/5 change is **not a code regression**: retrieval and grounding are unchanged.
Only the synthesis provider changed, and the PRD had never recorded which provider produced
the figure — so a key rotation silently invalidated a published number. The single failure is
a *false abstention* on "Who does Cincinnati Financial hold a stake in?" — 60 facts retrieved,
all 60 grounded, citations valid, and the model declined to answer. The superseded record's
metadata is preserved at `data/graphrag_rubric.PRIOR-anthropic.md`.

### 4.7 Graph analytics (GAE) — G8, deferred phase 2

Run graph algorithms (PageRank / centrality, WCC / SCC, community detection /
label propagation) over the graph via the ArangoDB **Graph Analytics Engine (GAE)**,
and expose an **agentic NL→insights** layer on top. Two layers, mirroring the query
side (transpiler + NL front-end):

- **Base (deterministic):** GAE jobs on `vertex_collections=["Node"]`,
  `edge_collections=["relations"]` — deploy → load → analyze → store → cleanup — with
  results written to **separate `gae_<algorithm>` collections** (never mutating `Node`)
  and recorded like the benchmark harness. The `create_graph.py` named graph was
  deliberately built to be GAE-targetable.
- **Top (agentic):** a requirements/NL → use-cases → algorithm-selection → execution →
  intelligence-report flow (LLM-driven), reusing the configured provider keys.

**Deployment finding (2026-07-29):** the cluster is an **ArangoDB Platform (ACP)**
deployment. A **self-managed** GAE engine deploys and deletes cleanly
(`/gen-ai/v1/graphanalytics`), so **GAE is available**. The per-engine compute route
(`/gral/<id>/v1/loaddata`) becomes live only ~30–60 s after deploy while the GRAL
ingress rolls out.

**Tooling decision:** integrate via **`agentic-graph-analytics`** — the repo/tool
(pip distribution `graph-analytics-ai`; import package `graph_analytics_ai`) — whose GAE
client is ACP-ready (readiness polling + retry on the transient `unknown path '/gral/..'`
signature) and which provides **both** the deterministic orchestrator
(`graph_analytics_ai/ai/workflow/orchestrator.py`) and the agentic layer
(`graph_analytics_ai/ai/agents/`), so the one tool covers both layers. The standalone **`graph-analytics-orchestrator`**
was evaluated and rejected for this cluster: it retries a failed load only ~3×/~12 s by
re-deploying (never waiting for ingress), so it 404s on ACP. Connection is self-managed
(reuses the `.env` ArangoDB endpoint + JWT; `GAE_DEPLOYMENT_MODE=self_managed`,
`ARANGO_DATABASE`), no extra credentials.

**Status (base — verified 2026-07-29):** the deterministic base is **implemented** in
[scripts/analytics.py](../scripts/analytics.py) (`import graph_analytics_ai`, runs under
`.venv311`) and **verified end-to-end** on the self-managed ACP GAE:

- **PageRank** — 114.8 s (deploy 69.8 s + load 14 s + compute 3.3 s + store/verify),
  3,099,773 result docs in `gae_pagerank` (field `rank`), ≈$0.013. Top-ranked nodes are
  the central financial concepts: `net income`, `revenue`, `net sale`, `operate income`,
  `fair value`, `gross margin`, … plus `new york stock exchange` (FIN_MARKET),
  `united state` (GPE) — `net income` (the biggest supernode) ranks #1.
- **WCC** — 91.5 s, 3,099,773 docs in `gae_wcc` (field `component`): **3,322 components**,
  one giant component of **3,091,396 nodes (99.7%)** with a small-component tail — the
  graph is essentially one connected structure.

Results are written to non-mutating `gae_<algorithm>` collections; raw summaries in
`data/analytics_<algorithm>_<db>.json`. The GRAL ingress-readiness 404 that blocked the
standalone orchestrator is handled here (readiness poll + transient-404 retry).

**Agentic planning layer (completes end-to-end 2026-07-30):** the **NL→plan** workflow
([scripts/analytics_agentic.py](../scripts/analytics_agentic.py) →
`WorkflowOrchestrator.run_complete_workflow`, LLM via OpenRouter) reads the
business-requirements doc, analyzes the schema, and **generates 10 GAE use cases**
mapped to algorithms (PageRank, WCC, label_propagation, betweenness, scc) — the analysis
*plan* — in ~23 s (`data/analytics_agentic/`). Two upstream bugs in
`agentic-graph-analytics` were fixed to get here: a `json.dump` missing `default=str`
(enum not serializable) and `steps.py` using `ExtractedRequirements.all_requirements`
(attr is `requirements`). This orchestrator's steps end at `save_outputs`, so it plans
but does **not** run the algorithms — GAE **execution** is the base layer above, which the
plan's algorithms feed into (all 5 selected algorithms are supported by `analytics.py`).

**Reporting (wired 2026-08-19, v0.20).** The package's report layer
(`graph_analytics_ai.ai.reporting`) generates insights, recommendations and **interactive
Plotly charts** from stored `gae_*` result collections via
[scripts/analytics_report.py](../scripts/analytics_report.py). That script exists because the
package's two halves do not meet: `GAEOrchestrator.run_analysis()` returns an
`AnalysisResult`, while `ReportGenerator.generate_report()` expects an `ExecutionResult`
wrapping an `AnalysisJob` — **no adapter ships with the package**, which is why the report
layer had never once run here. It reports on results that already exist: no engine is
deployed and no analysis re-run. Verified on `gae_pr_2024` → 88 KB HTML, 3 Plotly charts
(top influencers, rank distribution, cumulative), 3 insights, 3 recommendations.

Two caveats worth keeping in the PRD, because each one alone hid this capability for weeks:
**(1)** charts sit behind an *optional* plotly import — absent it, `reporting/__init__.py`
sets `_charts_available = False` and emits one `WARNING:root:` line, yielding a silently
chartless report; `analytics_report.py` therefore asserts `is_plotly_available()` and fails
loudly. **(2)** output is **HTML on disk**, not the platform's `aga_report_*` collections
(`aga_report_manifests` / `aga_report_sections` / `aga_chart_specs` remain 0). The generated
HTML loads plotly.js from a CDN, so it renders in a browser but not inside a CSP-restricted
embed.

**Pending (optional):** the **autonomous chaining** only — NL plan → GAE execute → report in
one flow (the tool's `graph_analytics_ai/ai/agents/` mode, or glue that feeds the agentic plan
into `analytics.py`); the report step above runs standalone on already-computed results. Also
pending: running the base across the OneShard/Smart distributions.

### 4.8 Time-travel (temporal) layer — G9

The corpus is 10 fiscal years (2014–2024) of 10-K observations, so the graph supports
point-in-time reconstruction. We adopt the valid-time interval model from the
`network-asset-management-demo` "TTL" blueprint (numeric validity fields + an MDI index
+ an as-of filter), **adapted to this LPG and read-only archive**:

- **No overlay collection.** Temporal validity lives **directly on the existing
  `relations` occurrence edges** — not on a derived `fact_relations` collection (an
  earlier proposal, dropped as unnecessary: at any instant a fact's per-filing fiscal
  spans are disjoint across years, so a plain as-of filter already returns the facts
  valid then; deduplication for diffs is a cheap in-query `COLLECT`).
- **Fields (numeric, for MDI `double`):** `validFrom`, `validTo` as **`YYYYMM`
  integers** (e.g. `201806`), derived in the DuckDB preprocess from `startDate` /
  `endDate`. `validTo` is **exclusive** (first month after the period end): a
  fiscal-year edge `2018-01…2018-12` stores `validFrom=201801, validTo=201901`.
  Open-ended / `default_end_timestamp` rows use the sentinel **`NEVER_EXPIRES = 999912`**.
  Nodes stay atemporal; a node's presence at `t` is derived from having any `relations`
  edge valid at `t`.
- **Query forms:** as-of `FILTER e.validFrom <= @t AND e.validTo > @t` (half-open);
  current/latest `FILTER e.validTo == @never_expires`; diff `t1→t2` = two as-of
  `COLLECT`s of `(ticker,_from,type,_to)` + `MINUS` → appeared / disappeared facts.

**Indexing — verified by the P0 `explain` spike (2026-08-07, live 3.12 cluster):**
- **MDI** `mdi` on `relations[validFrom, validTo]` (`fieldValueTypes:"double"`): a
  direct, non-node-anchored as-of scan **uses it**, temporal filter fully index-covered
  (`remove-filter-covered-by-index`).
- **Node-anchored** typed as-of (`_from == @n AND type == @r AND validFrom <= @t …`) is
  served by a **persistent composite index** `relations(_from, type, validFrom)` (+ the
  reverse `(_to, type, validFrom)`) — the optimizer picks it over the MDI
  (`move-filters-into-enumerate`), `validTo` a cheap residual in the narrow typed slice.
  These extend the §4.2 VCIs with a trailing `validFrom`.
- **Traversals do NOT engage the MDI** — a `p.edges[*] ALL <= @t` traversal uses only the
  built-in `edge` index and applies the temporal predicate as a per-edge post-filter
  (`optimize-traversals`), **exactly as the VCIs behave in traversals (§4.2, §8)**.
  Therefore as-of is expressed as **direct edge-collection queries**; multi-hop temporal
  uses `PRUNE (e.validFrom > @t OR e.validTo <= @t)` + per-edge `FILTER` to cut dead
  branches early (correct, edge-index-backed, not MDI-accelerated).

**Placement — `FinReflectKgTemporal`, OneShard.** A dedicated database keeps the additive
temporal fields + MDI from perturbing the frozen M4 benchmark baselines and lets the
encoding iterate without re-importing the large distributions. **OneShard** because the
perf-sensitive temporal path is the multi-hop as-of traversal, which the spike shows is
*not* index-accelerated — co-locating all edges on one DBServer removes cross-DBServer
`RemoteNode` hops (M4: OneShard ~4× faster on 2-hop), and a demo needs no horizontal
scale-out. Once the encoding is settled, `validFrom`/`validTo` fold into the shared ETL so
**all three distributions** inherit temporal and it becomes benchmarkable across placements
(the G7 lens). **TTL is deliberately not used** — this is a permanent historical archive,
not the blueprint's churn-aging demo (whose TTL physically deletes history).

**Validation (fixes the blueprint's gap — it checks document shape only):** occurrence-count
reconciliation; every as-of result ⊆ the loaded edges; spot-checks on known facts (e.g.
`aapl` `operates_in` `china` present as-of 2018, absent in a pre-entry year); `explain`
confirms MDI / composite-index usage. **Status: built & validated (M8, v0.15).** A
data-quality clamp folds OCR-noisy start years (absurd values like 1163/8176 that parse
cleanly) back to the filing year when outside [2013, 2026] — otherwise ~654 K edges (43 K
open-ended) would pollute every snapshot; `endDate` is left lenient so real far-future
maturities read as open-ended. Build: `scripts/build_temporal.sh`.

**Bitemporal analysis — G9-P3.** Filing `year` is the **transaction-time** axis (when a fact
was asserted) and `validFrom`/`validTo` the **valid-time** axis (when it held) — the graph is
bitemporal with no new fields. [scripts/restatements.py](../scripts/restatements.py) reports
**backward-looking assertions** (filing year − period start ≥ lag): **1.82 M edges (10.5 %)** are
backward-looking, led by utilities/insurers, enabling an "as-known-as-of" query. Two visualizer
saved queries (backward-looking + bitemporal known-from) are installed, gated by `ARANGO_TEMPORAL`.

**Temporal analytics — G9-P4.** Trend analysis across the decade of as-of snapshots.
[scripts/temporal_analytics.py](../scripts/temporal_analytics.py) computes per-as-of-year
centrality (in-degree), target-type topic shift, and biggest risers (covid-19 enters the 2020
top-10; cybersecurity risk / lease accounting / SEC rule rise 2014→2024). Since Pregel is
deprecated on this cluster, [scripts/temporal_pagerank.py](../scripts/temporal_pagerank.py)
computes per-year influence with **GAE PageRank** over materialized as-of snapshot edge
collections, compared across years. Snapshots rewire flagged generic-mention endpoints to
per-company bnodes and drop junk placeholders (`isJunkPlaceholder`); resume-skip is gated
on snapshot freshness so years stay comparable (v0.17). Live ranks: `net income` #1 in
2014 / 2019 / 2020 / 2024.

**Interactive demo — G9-P5.** A lightweight, **local, live** demo visualizer ([demo/](../demo/),
FastAPI + **vendored** Cytoscape.js, read-only vs `FinReflectKgTemporal`) makes the time-travel
layer explorable end-to-end. The as-of view renders a **connected neighbourhood of the company**
(depth 1 = the direct-facts star; a **Depth** control expands to 2–3 hops of context), with the
company node **pinned at the centre** and the whole decade scrubbable **DVR-style**: one
`/api/timeline` payload carries all years, the union is laid out once with stable positions, so
dragging the slider **crossfades** between years (facts glide / fade in / fade out) with no relayout.
A connected-component filter guarantees no free-floating concept↔concept islands. A **valid/reported
time toggle** switches the axis between valid-time (what *held* at mid-year, `validFrom`/`validTo`)
and transaction-time (what a filing *reported* that year, `year`) — the bitemporal P3 capability made
interactive. Overlays: an **influence-over-time** panel (top entities by GAE PageRank at the anchor
year nearest the slider, `gae_pr_2014/2019/2020/2024`); a **company explorer** with year-over-year
appeared/disappeared diffs and backward-looking disclosures (P3); a **Cleaned/Raw toggle** that
demonstrates the generic-mention cleanup (*Cleaned* drops junk placeholders and skolemizes
generic-mention hubs into per-company bnodes; *Raw* shows the graph as extracted); a **legend that
doubles as type filters**; and a **Top-N PageRank slider** that restricts the view to the most
globally-influential entities. Endpoints:
`/api/{years,tickers,asof,timeline,influence,prranks,diff,backward}`. Deliverables:
[demo/api.py](../demo/api.py), `demo/static/*`, [demo/screenshot.sh](../demo/screenshot.sh); run
`uvicorn demo.api:app`.

**Presentation (v1.4).** The demo uses the **ArangoDB brand palette adopted verbatim from the
r2g Studio** (`r2g/src/r2g/ui/static/index.html`) as CSS custom properties — including
`--arango-green #006532` and `--green #2fa86b` — with **light/dark theming on the same contract
as r2g**: light default, dark opt-in via `<html data-theme="dark">`, a header toggle showing the
icon for the mode you would switch *to*, persisted in `localStorage`, and resolved **pre-paint**
so there is no flash of the wrong theme. This is a deliberate cross-project consistency decision,
not a local style choice: the two UIs share one palette and one theme contract. Because
**Cytoscape bakes its stylesheet at construction**, the graph canvas cannot inherit CSS — so
`graphStyle()` reads the tokens via `getComputedStyle` and `applyTheme()` re-applies them with
`cy.style().fromJson(…).update()`, keeping canvas and chrome in step. Node marks carry a
**surface-coloured ring** and a raised minimum size (leaf floor 14→17 px, `arrow-scale` 0.7→0.55,
explicit `z-index` above edges) so a node always reads distinctly against its own edge, the
arrowhead, and neighbouring labels in both themes — the light-mode edge colour is also stepped
away from the default grey node hue.

**Visibility, selection and filter semantics (v1.5).** Three defects that all presented as
"the graph is wrong" had distinct causes, and the guard for the first was itself faulty.
(a) **Off-edge rendering** — Cytoscape resolves same-property conflicts by rule order, so the
`.off` rule must sort **after** the base `edge` rule or a hidden edge keeps painting at
`opacity: 0.75` while its node vanishes. Guarded by two counters in the header, because class
state and resolved style are different questions: `modelOrphans` (an edge we mean to show whose
endpoint is hidden) and `paintLeaks` (an edge we mean to hide that is still painted, read from
`e.style('opacity')`). The v1.4 counter tested only the former and so read 0 while the bug was
live. (b) **Depth ≥ 2 selection** — a company node is incident to ~99 % of its own
neighbourhood, so star and context edges are budgeted **separately** and each context edge is
taken with the shortest path anchoring it to the company, or the connected-component filter
strips it; both selection queries carry a deterministic `SORT e._key` so the rendered picture is
reproducible. `/api/asof` and `/api/timeline` share one selector. (c) **The Top-N PageRank filter
ranks corpus-wide**, not within the company, so it is labelled `global PageRank top N — X of Y
here` (for `aapl` 2018, top-200 keeps 20 of 219). Theme default is **light unconditionally** —
the OS `prefers-color-scheme` fallback is deliberately not consulted.
Deliverables: `demo/static/{index.html,style.css,app.js}`, [demo/api.py](../demo/api.py).

**Status: built (v1.5, v0.21).**

### 4.9 BYOC packaging of the demo UI — G10

The G9-P5 demo runs locally today (`uvicorn demo.api:app`, credentials from `.env`). The
ArangoDB **Contextual Data Platform** can host it as a **platform service** via **BYOC**
(bring-your-own-container), so the demo is reachable from the deployment itself rather than
a laptop. Evidence below is from
[arangodb/servicemaker](https://github.com/arangodb/servicemaker) — the packaging tool and
its Helm chart — not from the marketing post, which omits the runtime contract.

**Two deployment paths, and the names collide.** The platform offers *Bring Your Own
**Code*** — upload a `.tar.gz`, the platform builds it on a hardened base image — and *Bring
Your Own **Container*** — supply a Docker image URL. Both get abbreviated "BYOC"; the
first-party packaging skill (`package-for-arango-byoc-skill.md`, Emmet Allen) documents the
**Code** path. **We take the Code path**: it needs no container registry the platform can
pull from, and it is the flow the first-party tooling and skill actually target. The
Container path stays available if we later need a non-Python runtime.

**The contract is small.** Serve HTTP on **port 8000** at the **root path**. Dependencies via
**`uv`**, declared in a **`pyproject.toml`**. `servicemaker` wraps the project into an image
derived from the base image, and emits a Helm chart plus the `project.tar.gz` that the
Container Manager consumes (found under `target/<project>/`). Manual packaging is supported
too: a `pyproject.toml` plus `main.py`, then `tar -czf myservice.tar.gz <project_dir>/`.

**Python 3.13, via `arangodb/py13base:latest`.** The skill is right and the public
`servicemaker` repo is behind it: `baseimages/` and `imagelist.txt` still name only the 3.12
images and `src/main.rs` hard-codes `py12base`, but **`arangodb/py13base:latest` is on Docker
Hub** (Python 3.13.13) and is verified working — `gdelt-market-impact` runs both deployment
paths on it. Two consequences: the skill's ARM64 fallback ("build `Dockerfile.py13base`
locally") cannot be followed literally because that file is not in the public repo, and it is
not needed; and **`py12base` does not ship `uv` at all**, which is a second reason to stay on
3.13.

**Routing forwards the prefix intact — CORRECTED 2026-09-26.** The service is published at
`/_service/uds/_db/<db>/<instance>/` and the request arrives with that prefix still on it.
The earlier claim that envoy rewrites it away was wrong. The app strips it itself
([demo/prefix.py](../demo/prefix.py)), the Starlette way: append to `root_path`, never shorten
`path` — shortening breaks `StaticFiles` on Starlette >= 0.33. **The browser half is separate
and also required.** Any absolute asset or
API URL in the frontend (`/app.js`, `/api/…`) resolves to the domain root, misses the
prefix, and 404s. **All frontend URLs must be relative.**

**Credentials are baked into the artifact — the platform does not inject them.**
Confirmed with Emmet Allen, 2026-08-26, and it contradicts the announcement's "handles
authentication automatically": a deployed service uses whatever it was **built** with; there is
no injection step. The chart injects only `PORT`. So the artifact carries `.env`, and
**the artifact becomes the secret** — a `.tar.gz` is one command from plaintext and an image is
`docker save` plus an untar, so either must be handled exactly like `.env` itself. The
mitigations that work (proven in `gdelt-market-impact/deploy/`): credential-free by default with
an explicit, warning `--with-env` flag; `*.tar.gz` gitignored; credential-bearing images
labelled and refused for push without an explicit acknowledgement env var; and if one escapes,
**rotate the database password** — deleting a tag does not purge layers from caches and
registries. If Container Manager later gains deploy-time environment variables, prefer them: the
artifact stops being a secret and rotation stops meaning a rebuild.

*A JWT path exists but is a service-design choice, not platform-provided credentials.* The route
sets `authentication: {type: required, passMode: pass}`, so envoy authenticates the caller and
forwards the `Authorization` header; a service **may** therefore connect as the caller
(`auth_method="jwt", user_token=token`), which is what `servicemaker`'s `arango-test-service`
does, reading its coordinator URL from `ARANGO_DEPLOYMENT_ENDPOINT`. That is strictly better —
no secret in the artifact, and queries respect the caller's own RBAC — but it is a data-path
refactor here, since [scripts/arango.py](../scripts/arango.py) binds credentials at module scope
and signs Basic auth. Baking is the shorter path to a working deployment; JWT pass-through is the
better end state.

**Conformance of the current demo.**

| Requirement | Status |
|---|---|
| HTTP at root path | **met** — `StaticFiles` mounted at `/` |
| No CDN dependency | **met** — Cytoscape vendored at `demo/static/vendor/` |
| Port 8000, bind `0.0.0.0` | **gap** — 8080 via the uvicorn CLI, no in-process entrypoint |
| Relative frontend URLs | **gap** — `/api/…`, `/style.css`, `/app.js`, `/vendor/…` are absolute |
| Credentials available at runtime | **gap** — needs `.env` baked in (`--with-env`), which makes the artifact a secret; or a JWT-pass-through refactor |
| Python entrypoint script | **gap** — started via the uvicorn CLI |
| `pyproject.toml` with `uv` deps | **gap** — the demo declares deps in `demo/requirements.txt`; the Code path needs a `pyproject.toml`, with nothing in optional extras |

**Reuse the working scaffolding.** `gdelt-market-impact/deploy/` already implements both
paths against `py13base` and is **verified running** against its live database (both routes
answer `/` and an API endpoint). Its author notes nothing there is GDELT-specific beyond two
`COPY` lines and one copy list, and names FinReflectKG as the reuse target. Crucially our demo
has the **same sibling-import shape** that its `package.sh` exists to solve —
[demo/api.py](../demo/api.py) does `sys.path.insert(0, ROOT/"scripts")` then
`from arango import req`, exactly as its `app/main.py` imports `scripts/_common.py` — so the
tree-reassembly logic ports directly rather than needing to be rediscovered. Porting that
scaffolding is the plan of record; writing our own is not.

**Packaging gotchas (from the first-party skill, plus what `gdelt-market-impact` hit).**
- **Build `linux/amd64` explicitly.** On Apple Silicon an arm64 image **pushes without
  complaint and then does not start** — a silent failure, so pass `--platform linux/amd64`
  rather than relying on the skill's build-the-base-image-locally alternative.
- **`uv` is not on `PATH` inside a `RUN` layer** — it lives in `~/.local/bin`, so a non-login
  shell cannot see it and the build dies as a bare `exit 127`. Source
  `/home/user/.local/bin/env` first.
- **There is no `pip` in the venv** (the base is deliberately stripped). Use
  `uv pip install -c /home/user/constraints.txt`, which also stops an added package floating a
  version away from what the pre-scanned base pins.
- **Quoted values in `.env` bite asymmetrically.** `python-dotenv` strips surrounding quotes;
  `docker run --env-file` does not. The symptom is `[HTTP 401] bad username/password`, which
  points nowhere near the cause — strip quotes defensively when reading config.
- **`.dockerignore` the data directories** or the daemon copies the corpus on every build.
- **ServiceMaker assumes one project directory and one entrypoint**, so a repo with sibling
  imports needs a reassembled self-contained tree; flattening it builds fine and fails at
  import time inside the platform.
- **`uv sync --extra` is unsupported** by `servicemaker` — every needed package must sit in the
  main `dependencies` array of `pyproject.toml`, not in an optional-extras group.
- **ARM64 hosts** may pull an AMD64 base image and fail; build the base image locally first
  (subject to the version caveat above).
- **Scoping** is chosen at deploy time: *Global* (hosted on `_system`, reachable from every
  database) or *database-specific* for an isolated workload. The demo is read-only against
  `FinReflectKgTemporal`, so database-specific is the tighter fit.
- **Multiple instances of one version** in a single database need a distinct
  `app_instance_name`.
- **Deployment metadata** at upload: file name, semantic version, and the service URL path
  (the `<name>` in `/_service/uds/_global/<app>/`).

**Built and verified, 2026-08-26.** Both artifact shapes exist and both work; see
[deploy/README.md](../deploy/README.md) for the operator-facing version.

| Path exercised | Result |
|---|---|
| Credential-free image, no environment | Boots; static UI and `/api/years` 200; database endpoints **503** naming the missing variables |
| Credential-free image + runtime env vars | Full database access |
| `build.sh --with-env` image, **no env passed** | Full database access — this is the actual deployment condition |
| `package.sh` tarball extracted into a bare `py13base` | Full database access |
| Live platform deployment | Serving, authenticated, real data through the stripped prefix |

Live: <https://20hin6od.rnd.pilot.arango.ai/_service/uds/_global/finreflect/> (deployed by
Emmet Allen; the platform gates it behind its own auth, so an unauthenticated request is a
401 from envoy, not from the service).

**The URL base is derived from `location.pathname`, not `document.baseURI`.** baseURI drops
the last path segment, so a service reached *without* its trailing slash resolves one
directory too high and 404s. [demo/static/app.js](../demo/static/app.js) tests for a `.` in
the final segment to tell a file leaf (`index.html`) from a directory leaf served bare. This
helper came from the deployed build and replaced an earlier baseURI version that carried
exactly that defect.

**A latent defect this work surfaced (beyond BYOC).**
[scripts/arango.py](../scripts/arango.py) read `.env` **unconditionally at import**, so the
credential-free image exited 1 before serving anything at all — including endpoints that touch
no database. More broadly, the application could never run from environment variables alone,
which every container deployment requires. `.env` is now optional, and an unset endpoint raises
`NotConfigured` at *call* time — surfaced as a 503 naming what is missing — instead of killing
the process at import. Quoted values from `docker run --env-file` are also stripped now, since
`--env-file` (unlike python-dotenv) preserves quotes and the symptom is a 401 pointing nowhere
near the cause.

**DEPLOYED 2026-09-26.** Live at
`https://prod.demo.pilot.arango.ai/_service/uds/_db/FinReflectKgTemporal/finreflect/`
(service `arango-user-defined-iu37r`, package `finreflectkg-timetravel` v1.0.0-1, base image
`py12base`). Deploy, roll back or remove it with the shared
[`arango-byoc-deploy`](https://github.com/ArthurKeen/arango-byoc-deploy) tool, configured in
[`arango-byoc.toml`](../arango-byoc.toml) and run through [scripts/byoc-deploy](../scripts/byoc-deploy):

```
./deploy/package.sh 1.0.0 --with-env          # flat bundle, credentials baked (SECRET)
scripts/byoc-deploy update                    # pre-flight, upload, swap, verify
```

Verified on the live URL, not just by the deploy script's own client: 743 companies; anchors
2014/2019/2020/2024; aapl-2020 depth-1 → 125 nodes / 140 edges; msft-2024 depth-2 → 146 / 197;
aapl 2019→2024 diff → 40 appeared / 40 disappeared; `style.css`, `app.js` and
`vendor/cytoscape.min.js` all served under the prefix.

**Why this took two attempts.** The August work was never tested against the platform — only
against a hand-run container — so it encoded the container-image contract instead of the package
one. Three assumptions were wrong (flat vs wrapped, `py12base` vs `py13base`, prefix forwarded vs
stripped), and the repo had no deploy script at all while five sibling projects did. The fix was
to read what actually works: `project-sentinel`, `gdelt-market-impact`,
`agentic-graph-analytics`, `arango-ontoextract` and `multihop-eval` are all deployed on this
cluster, all on `py12base`, all flat, all stripping the prefix in-app.

**The mount database must exist.** The `<db>` segment comes from what the app reads
(`FinReflectKgTemporal`, hardcoded in [demo/api.py](../demo/api.py)), deliberately not from the
repo's `ARANGO_DATABASE` — which reads `FinReflectKG`, a database that does not exist on
prod.demo after the migration and would mount the service at a dead path.

**Expect a ~60s 404 window** after the service reports DEPLOYED while the pod installs its
dependencies. Poll rather than concluding failure.

**Applies to more than this repo.** `gdelt-market-impact`'s what-if UI is the same shape
(FastAPI + vendored Cytoscape over ArangoDB) and already binds **port 8000** at the root
path with assets vendored locally — it is BYOC-shaped already and needs only the URL and
auth changes. The packaging work should be designed once and applied to both.

**Status: designed, not built (G10, v0.22).**

## 5. Sizing (from data analysis)

See [data-analysis.md](data-analysis.md) for measured numbers, [load-report.md](load-report.md)
for the as-loaded counts. Headline figures: **17,513,372 edges**, **3,099,773 nodes**
(distinct name+type pairs), **1,384,513 chunks loaded** (of 1,403,652 distinct chunk
keys — rows with `has_context = false` carry no chunk); raw parquet 1.67 GB;
ArangoDB footprint dominated by the `relations` collection and its two VCIs
plus ~4 GB of deduplicated chunk text. The SmartGraph "Design 2" build (§4.5) grew
nodes to **6,658,668** (2.1×) via per-company concept duplication.

## 6. Benchmark sketch (G5)

Representative query classes to time once loaded (exact suite to be agreed
later). Per §4.2, typed 1-hop classes are expressed as **direct
edge-collection queries** (the access path that engages the VCIs), not pattern
traversals:

1. **Point lookup**: node by `name`.
2. **1-hop typed (direct edge query)**: all `operates_in` edges from a company
   node → GPE nodes (engages VCI 1, `vci_from_type_totype`).
3. **Reverse typed (direct edge query)**: who `has_stake_in` a given target
   (engages VCI 2, `vci_to_type_fromtype`).
4. **Supernode handling**: high-degree metric nodes (e.g. `net income`, in-degree
   ~10⁵) — direct edge query scans only matching edges (59,315 for `net income`)
   vs. an unpruned pattern traversal scanning all ~10⁵; the core demonstration of
   why the VCI access path matters here.
5. **k-hop path**: company → supplier/competitor chains, depth 2–3 (pattern
   traversal; edge-index + filter cost accepted).
6. **Temporal slice**: edges for a ticker filtered by `year` range.
7. **NL-grounding join**: edge → `chunks` text retrieval latency.

**Cross-distribution comparison (G7):** run the suite against `FinReflectKG`
(flexible 1-shard), `FinReflectKgOneShard` (OneShard), and `FinReflectKgSmart`
(SmartGraph) to quantify the effect of placement — especially OneShard eliminating
the cross-DBServer `RemoteNode` hops seen on the baseline's multi-hop traversals.
Note: latency on the shared remote cluster is noisy (a single query has ranged
203 ms–20 s across runs), so use **scanned-edge counts** and **shard-locality from
`explain`** as the deterministic metrics; reserve wall-clock for a quiescent window.

## 7. Milestones

| M | Deliverable | Notes | Status |
|---|-------------|-------|--------|
| M1 | PRD + data analysis + ETL plan reviewed | this document set | Done |
| M2 | Download + preprocess pipeline producing JSONL | local, repeatable | Done |
| M3 | Bulk load into remote ArangoDB + indexes + reconciliation report | G1–G4 | **Done** ([load-report.md](load-report.md)) |
| M4 | Benchmark suite + results | G5 (+ G7 cross-distribution) | **Done** — cross-distribution suite + results ([benchmark-report.md](benchmark-report.md)); SmartGraph decomposes the `net income` supernode ~250× on per-company queries; latency indicative on the shared cluster |
| M5 | NL-query evaluation (Cypher→AQL / NL→Cypher via `arango-cypher-py` + GraphRAG) | G6, §4.6 | **Done (FinReflectKG-side)** — schema-aware **NL→Cypher front-end** run ([scripts/nl2cypher_eval.py](../scripts/nl2cypher_eval.py)): **19/22 transpile · 9/22 execute · 0 `MAPPING_NOT_FOUND`** (vs 14/22 · 7/22 for hand-written Cypher, [scripts/cypher_eval.py](../scripts/cypher_eval.py)). **GraphRAG answer synthesis 4/5** (`openai/gpt-4o`, 2026-08-13; the one failure is a false abstention on the CINF stake question — 60 facts retrieved, all grounded, citations valid, model declined to answer. Was 5/5 on `anthropic/claude-sonnet-4-5`, no longer reproducible: that key is revoked) ([scripts/graphrag_rubric.py](../scripts/graphrag_rubric.py)). Root-caused the gold-set vocabulary mismatch against live data (sibling-schema rename `:RISK`→`RISK_FACTOR`; `ORG_REG` real but capped out of the top-20 ontology; `:METADATA` absent). Remaining upstream: transpiler ERR 1511 (multi-`WITH`), non-VCI AQL efficiency, analyzer entity cap, `reduce()` ([nl-graphrag.md](nl-graphrag.md)) |
| M6 | Multi-distribution builds (OneShard + SmartGraph) | G7 | **Done** — OneShard and SmartGraph both built & verified ([multi-distribution-plan.md](multi-distribution-plan.md)) |
| M7 | Graph analytics via GAE (deterministic jobs + agentic NL→insights) | G8, §4.7 | **Partial** — base verified (PageRank + WCC on 3.1 M nodes, [scripts/analytics.py](../scripts/analytics.py)); agentic planning completes (NL → 10 use cases, [scripts/analytics_agentic.py](../scripts/analytics_agentic.py)); autonomous execute→report loop optional/pending |
| M8 | Time-travel layer (`FinReflectKgTemporal`, OneShard) | G9, §4.8 | **Done** — built via [scripts/build_temporal.sh](../scripts/build_temporal.sh) (augment → OneShard import → MDI + composite VCIs → graph → validate); 17,513,372 edges, validation green. Includes a data-quality clamp on OCR-noisy start years (§4.8) |
| M9 | BYOC service deployment | Container image **and** code package both build; service boots credential-free and serves; database access verified via baked `.env`, via runtime environment variables, and from the extracted tarball in a bare `py13base`; live on the pilot platform | **DONE** 2026-08-26 |

## 8. Risks & open questions

| Risk / question | Mitigation / decision needed |
|---|---|
| Supernodes (generic `FIN_METRIC` targets like `net income` accumulate in-degree across all companies/years) | **Direct edge-collection queries** prune by `type`+`_toType`/`_fromType` via the VCIs (verified: `net income` scans 59,315 not ~10⁵); benchmark explicitly (§6.4). The SmartGraph "Design 2" build (§4.5) scopes concept copies per ticker, the phase-2 option now in flight |
| **SmartGraph shared-concept modeling** — split concept identity under Design 2 | **Resolved: Design 2** (locked 2026-06-29). Accepted cost = global cross-company concept queries aggregate `BY name`; monitored per [multi-distribution-plan.md](multi-distribution-plan.md) §5.7 — fall back to Design B only if global-concept rollups dominate the workload |
| VCIs do **not** accelerate pattern traversals on 3.12.x cluster (only direct edge queries) | Write typed 1-hop queries as direct edge-collection queries (§4.2); reserve traversals for variable-depth paths |
| Benchmark latency noisy on shared remote cluster (203 ms–20 s for one query) | Use scanned-edge counts + `explain` shard-locality as deterministic metrics; wall-clock only in a quiescent window |
| Same name with multiple types (~14% of names, measured) becomes multiple nodes | Accepted: node identity = `(name, type)`; consistent with edges carrying `_fromType`/`_toType` |
| One edge per occurrence (17.51 M) vs deduplicated facts (8.49 M distinct e/r/t, measured) | Keep per-occurrence edges (provenance + temporal value is the dataset's point); a deduplicated "fact" layer can be derived later if benchmarks need it |
| Remote import throughput (TLS, WAN) | Batch + parallel `arangoimport`; measure on a 1-shard pilot before full run |
| `start_date`/`end_date` are strings (`"January 2014"`, `default_end_timestamp`) | Parse to ISO `yyyy-mm` during preprocessing; keep raw value in a sibling field |
| Time-travel traversals (`p.edges[*] ALL`) do **not** engage the MDI on 3.12.x (edge-index + post-filter — verified P0 spike) | Express as-of as **direct edge queries** (MDI / composite-index backed); use `PRUNE` for multi-hop temporal — same access-path discipline as the VCIs (§4.2/§4.8) |
| Temporal encoding: reporting-period dates are month-granular, ~4% open-ended, occasionally noisy/multi-year | `validFrom`/`validTo` as `YYYYMM` ints (exclusive `validTo`); `default_*`/open → `NEVER_EXPIRES=999912`; validate as-of results against known facts, not raw dates (§4.8) |
| Dataset license is NC | POC/research use only; revisit before productization |

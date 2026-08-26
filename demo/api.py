"""FinReflectKG Time-Travel demo — FastAPI backend (live against FinReflectKgTemporal).

Serves the custom demo visualizer (G9/§4.8): time-slider as-of subgraphs, influence-over-time
(GAE PageRank per anchor year), and a company explorer (year-over-year diff + backward-looking
disclosures). Generic-mention junk placeholders are excluded so the graph reflects the cleaned
topology. Read-only. Talks to Arango via `arango_client` (local `.env` Basic auth, or
BYOC `ARANGO_DEPLOYMENT_ENDPOINT` + JWT). Self-contained — no `scripts/` import — so
the demo directory can be packed as a Container Manager `.tar.gz`.

Local:  .venv/bin/python -m uvicorn demo.api:app --port 8080
BYOC:   python main.py   # 0.0.0.0:8000, see demo/main.py
"""
from __future__ import annotations

import pathlib
import sys

_DIR = pathlib.Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

from arango_client import database, endpoint, parse_bearer, req, request_token  # noqa: E402
from fastapi import FastAPI, HTTPException, Query, Request  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from starlette.middleware.base import BaseHTTPMiddleware  # noqa: E402

ANCHORS = [2014, 2019, 2020, 2024]   # years with a materialized GAE PageRank (gae_pr_<year>)
YEAR_MIN, YEAR_MAX = 2014, 2024

app = FastAPI(title="FinReflectKG Time-Travel Demo")


class _BindRequestAuth(BaseHTTPMiddleware):
    """Forward the inbound Bearer token to Arango (Container Manager proxy pattern)."""

    async def dispatch(self, request: Request, call_next):
        token = parse_bearer(request.headers.get("authorization"))
        reset = request_token.set(token)
        try:
            return await call_next(request)
        finally:
            request_token.reset(reset)


app.add_middleware(_BindRequestAuth)


def aql(query, bind=None, timeout=60):
    st, b = req(
        "POST",
        "/_api/cursor",
        {"query": query, "bindVars": bind or {}, "batchSize": 50000},
        db=database(),
        timeout=timeout,
    )
    if st not in (200, 201):
        raise HTTPException(status_code=502, detail=f"AQL {st}: {b.get('errorMessage')}")
    result = b.get("result", [])
    cid = b.get("id")
    while b.get("hasMore") and cid:  # page the cursor — default batches cap at 1000 rows
        st, b = req("PUT", f"/_api/cursor/{cid}", None, db=database(), timeout=timeout)
        if st not in (200, 201):
            raise HTTPException(status_code=502, detail=f"AQL cursor {st}: {b.get('errorMessage')}")
        result.extend(b.get("result", []))
    return result


_flagged_ids = None


def flagged_ids():
    """Cached set of flagged node _ids (generic-mention + junk placeholder), so the as-of
    sample can surface flagged-touching edges first without per-edge DOCUMENT lookups."""
    global _flagged_ids
    if _flagged_ids is None:
        _flagged_ids = aql("FOR n IN Node FILTER n.isGenericMention == true OR n.isJunkPlaceholder == true RETURN n._id")
    return _flagged_ids


@app.get("/api/years")
def years():
    return {"min": YEAR_MIN, "max": YEAR_MAX, "anchors": ANCHORS}


@app.get("/api/tickers")
def tickers():
    """All companies, most-connected first (for the picker)."""
    return aql("FOR e IN relations COLLECT tk = e.ticker WITH COUNT INTO c SORT c DESC RETURN tk")


@app.get("/api/asof")
def asof(ticker: str, year: int, limit: int = 140, clean: bool = True, depth: int = 1):
    """A company's subgraph valid as-of mid-<year>, as a depth-bounded neighborhood of the
    company node — so the view is always connected (no free-floating concept<->concept islands).

    depth=1 (default): the company's direct facts (a clean star). depth>=2: also facts among
    those neighbors, still reachable from the company. clean=True: drop junk placeholders and
    skolemize generic-mention hubs into per-company bnodes; clean=False: the RAW extraction.
    """
    t = year * 100 + 6
    flagged = flagged_ids()

    if depth <= 1:
        # one round-trip for total + focal (the company = highest-degree endpoint), one for the star
        meta = aql("""LET es = (FOR e IN relations FILTER e.ticker==@tk AND e.validFrom<=@t AND e.validTo>@t
                                   RETURN [e._from, e._to])
                      RETURN {total: LENGTH(es),
                              focal: FIRST(FOR p IN es FOR s IN p COLLECT id = s WITH COUNT INTO c
                                             SORT c DESC LIMIT 1 RETURN id)}""",
                   {"tk": ticker, "t": t})[0]
        total, focal = meta["total"], meta["focal"]
        if not focal:
            return {"ticker": ticker, "year": year, "clean": clean, "depth": depth,
                    "focal": None, "nodes": [], "edges": [], "shown": 0, "total": total}
        rows = aql("""
            LET flagged = @flagged
            FOR e IN relations
              FILTER e.ticker == @tk AND e.validFrom <= @t AND e.validTo > @t
                 AND (e._from == @focal OR e._to == @focal)   /* incident to the company -> pure star */
              SORT (e._to IN flagged OR e._from IN flagged) ? 0 : 1
              LIMIT @lim
              LET df = DOCUMENT(e._from) LET dt = DOCUMENT(e._to)
              RETURN {f:e._from, fn:df.name, ft:df.type, fj:df.isJunkPlaceholder, fg:df.isGenericMention, fr:df.roleLemma,
                      t:e._to, tn:dt.name, tt:dt.type, tj:dt.isJunkPlaceholder, tg:dt.isGenericMention, tr:dt.roleLemma,
                      rel:e.type}""",
            {"tk": ticker, "t": t, "lim": limit, "flagged": flagged, "focal": focal})
    else:
        # depth>=2: pull the ticker's as-of edges once, derive total + focal in Python, then
        # delegate the depth-bounded selection to _select_neighborhood (below) — the single
        # source of truth. This endpoint previously carried its own copy of that logic, which
        # meant the star-vs-context budget defect had to be fixed in two places and was only
        # ever fixed in one. Done in Python because an `e._from IN keep` AQL filter would use
        # the edge index to fetch those nodes' edges GLOBALLY, and neighbours include
        # supernodes (net income ~60k) -> a full-graph blowup + timeout.
        flagged_set = set(flagged)
        triples = aql("""FOR e IN relations FILTER e.ticker==@tk AND e.validFrom<=@t AND e.validTo>@t
                           SORT e._key
                           RETURN {f:e._from, t:e._to, rel:e.type}""", {"tk": ticker, "t": t})
        total = len(triples)
        if not triples:
            return {"ticker": ticker, "year": year, "clean": clean, "depth": depth,
                    "focal": None, "nodes": [], "edges": [], "shown": 0, "total": 0}
        deg = {}
        for e in triples:
            deg[e["f"]] = deg.get(e["f"], 0) + 1
            deg[e["t"]] = deg.get(e["t"], 0) + 1
        focal = max(deg, key=deg.get)
        sel = _select_neighborhood(triples, focal, depth, limit, flagged_set)
        ids = list({e["f"] for e in sel} | {e["t"] for e in sel})
        docs = {}
        if ids:
            for row in aql("""FOR id IN @ids LET n = DOCUMENT(id)
                                RETURN {id: id, name:n.name, type:n.type, junk:n.isJunkPlaceholder,
                                        gen:n.isGenericMention, role:n.roleLemma}""", {"ids": ids}):
                docs[row["id"]] = row
        rows = [{"f":e["f"], "fn":docs.get(e["f"],{}).get("name"), "ft":docs.get(e["f"],{}).get("type"),
                 "fj":docs.get(e["f"],{}).get("junk"), "fg":docs.get(e["f"],{}).get("gen"), "fr":docs.get(e["f"],{}).get("role"),
                 "t":e["t"], "tn":docs.get(e["t"],{}).get("name"), "tt":docs.get(e["t"],{}).get("type"),
                 "tj":docs.get(e["t"],{}).get("junk"), "tg":docs.get(e["t"],{}).get("gen"), "tr":docs.get(e["t"],{}).get("role"),
                 "rel":e["rel"]} for e in sel]

    def endpoint(idv, name, typ, junk, gen, role):  # -> (id, label, type, is_bnode, is_junk)
        if clean and gen and role:
            return f"bnodes/bn_{ticker}_{role}", role, role.upper(), True, False
        return idv, name, typ, False, bool(junk)

    nodes, edges = {}, []
    for r in rows:
        fid, fn, ft, fb, fj = endpoint(r["f"], r["fn"], r["ft"], r.get("fj"), r.get("fg"), r.get("fr"))
        tid, tn, tt, tb, tj = endpoint(r["t"], r["tn"], r["tt"], r.get("tj"), r.get("tg"), r.get("tr"))
        if clean and (fj or tj):
            continue  # drop junk-placeholder edges
        nodes.setdefault(fid, {"id": fid, "label": fn, "type": ft, "bnode": fb, "junk": fj})
        nodes.setdefault(tid, {"id": tid, "label": tn, "type": tt, "bnode": tb, "junk": tj})
        edges.append({"source": fid, "target": tid, "label": r["rel"]})
    return {"ticker": ticker, "year": year, "clean": clean, "depth": depth, "focal": focal,
            "nodes": list(nodes.values()), "edges": edges, "shown": len(edges), "total": total}


def _select_neighborhood(ye, focal, depth, limit, flagged):
    """Depth-bounded, always-connected edge selection over a year's edge list `ye` (each {f,t,rel}).
    depth 1 = edges incident to focal (star). depth>=2 = BFS to <depth> hops, both-endpoints-in-keep,
    flagged-first, bigger budget the deeper you go, then filtered to the focal's connected component."""
    fk = lambda e: 0 if (e["f"] in flagged or e["t"] in flagged) else 1
    if depth <= 1:
        return sorted((e for e in ye if e["f"] == focal or e["t"] == focal), key=fk)[:limit]
    adj = {}
    for e in ye:
        adj.setdefault(e["f"], set()).add(e["t"])
        adj.setdefault(e["t"], set()).add(e["f"])
    keep, frontier = {focal}, {focal}
    for _ in range(depth):
        nxt = set()
        for n in frontier:
            nxt |= adj.get(n, set())
        nxt -= keep
        keep |= nxt
        frontier = nxt
        if len(keep) > 800:
            break
    # Budget the star and the context SEPARATELY, and make context selection ANCHOR-AWARE.
    # A company node is incident to ~99% of its own neighbourhood's edges (aapl 2021: 2,004
    # of 2,024), so a blind slice spends the whole budget on the star and returns zero
    # multi-hop edges — depth 2/3 then look identical to depth 1, just denser. Reserving a
    # flat context quota is not enough either: the connected-component filter below then
    # strips any context edge whose endpoints lost their path to focal when the star was
    # trimmed. So each context edge is taken together with the shortest path that anchors it
    # back to focal, which makes it survive that filter by construction.
    ranked = sorted((e for e in ye if e["f"] in keep and e["t"] in keep), key=fk)
    is_star = lambda e: e["f"] == focal or e["t"] == focal
    star = [e for e in ranked if is_star(e)]
    ctx = [e for e in ranked if not is_star(e)]
    budget = limit + (depth - 1) * 60
    ctx_allow = min(len(ctx), max(40, (depth - 1) * 60))

    # BFS from focal over every candidate, recording the parent edge, so any kept node can
    # walk a shortest path home. Works at any depth (a depth-3 context edge may be anchored
    # through an intermediate hop, not directly to focal).
    padj = {}
    for e in ranked:
        padj.setdefault(e["f"], []).append((e["t"], e))
        padj.setdefault(e["t"], []).append((e["f"], e))
    prev, fr = {focal: None}, [focal]
    while fr:
        nxt = []
        for n in fr:
            for m, e in padj.get(n, ()):
                if m not in prev:
                    prev[m] = (n, e); nxt.append(m)
        fr = nxt

    def path_home(n):
        out = []
        while prev.get(n):
            p, e = prev[n]; out.append(e); n = p
        return out

    ekey = lambda e: (e["f"], e["rel"], e["t"])
    cand, seen = [], set()

    def take(e):
        k = ekey(e)
        if k in seen:
            return
        seen.add(k); cand.append(e)

    ctx_used = 0
    for e in ctx:
        if ctx_used >= ctx_allow or len(cand) >= budget:
            break
        bundle = [e] + [pe for n in (e["f"], e["t"]) for pe in path_home(n)]
        fresh = sum(1 for b in bundle if ekey(b) not in seen)
        if len(cand) + fresh > budget:
            continue                      # this bundle will not fit; try a cheaper one
        for b in bundle:
            take(b)
        ctx_used += 1
    for e in star:                        # fill the remainder with the star, flagged-first
        if len(cand) >= budget:
            break
        take(e)

    nadj = {}
    for e in cand:
        nadj.setdefault(e["f"], set()).add(e["t"])
        nadj.setdefault(e["t"], set()).add(e["f"])
    reach, fr = {focal}, [focal]
    while fr:
        n = fr.pop()
        for m in nadj.get(n, ()):
            if m not in reach:
                reach.add(m); fr.append(m)
    return [e for e in cand if e["f"] in reach and e["t"] in reach]


@app.get("/api/timeline")
def timeline(ticker: str, depth: int = 1, clean: bool = True, axis: str = "valid", limit: int = 140):
    """All years' subgraphs in one payload, so the client can scrub the slider smoothly (DVR): it
    lays the union out once and crossfades between years. axis='valid' -> valid-time (what held at
    mid-year); axis='reported' -> transaction-time (facts a filing asserted that year, e.year==Y)."""
    flagged = set(flagged_ids())
    edges = aql("""FOR e IN relations FILTER e.ticker==@tk
                     SORT e._key
                     RETURN {f:e._from, t:e._to, rel:e.type, vf:e.validFrom, vt:e.validTo, yr:e.year}""",
                {"tk": ticker}, timeout=120)
    if not edges:
        return {"ticker": ticker, "focal": None, "depth": depth, "clean": clean, "axis": axis, "years": {}}
    deg = {}
    for e in edges:
        deg[e["f"]] = deg.get(e["f"], 0) + 1
        deg[e["t"]] = deg.get(e["t"], 0) + 1
    focal = max(deg, key=deg.get)                    # the company: highest-degree endpoint overall
    sel_by_year, all_ids = {}, set()
    for Y in range(YEAR_MIN, YEAR_MAX + 1):
        if axis == "reported":
            ye = [e for e in edges if e["yr"] == Y]
        else:
            tt = Y * 100 + 6
            ye = [e for e in edges if e["vf"] <= tt and e["vt"] > tt]
        sel = _select_neighborhood(ye, focal, depth, limit, flagged)
        sel_by_year[Y] = (sel, len(ye))
        for e in sel:
            all_ids.add(e["f"]); all_ids.add(e["t"])
    docs = {}
    if all_ids:
        for row in aql("""FOR id IN @ids LET n = DOCUMENT(id)
                            RETURN {id: id, name:n.name, type:n.type, junk:n.isJunkPlaceholder,
                                    gen:n.isGenericMention, role:n.roleLemma}""", {"ids": list(all_ids)}, timeout=120):
            docs[row["id"]] = row

    def endpoint(idv):  # -> (id, label, type, is_bnode, is_junk)
        d = docs.get(idv, {})
        if clean and d.get("gen") and d.get("role"):
            role = d["role"]
            return f"bnodes/bn_{ticker}_{role}", role, role.upper(), True, False
        return idv, d.get("name"), d.get("type"), False, bool(d.get("junk"))

    years = {}
    for Y, (sel, total) in sel_by_year.items():
        nodes, elist = {}, []
        for e in sel:
            fid, fn, ft, fb, fj = endpoint(e["f"])
            tid, tn, tt2, tb, tj = endpoint(e["t"])
            if clean and (fj or tj):
                continue
            nodes.setdefault(fid, {"id": fid, "label": fn, "type": ft, "bnode": fb, "junk": fj})
            nodes.setdefault(tid, {"id": tid, "label": tn, "type": tt2, "bnode": tb, "junk": tj})
            elist.append({"source": fid, "target": tid, "label": e["rel"]})
        years[str(Y)] = {"nodes": list(nodes.values()), "edges": elist, "shown": len(elist), "total": total}
    return {"ticker": ticker, "focal": focal, "depth": depth, "clean": clean, "axis": axis, "years": years}


@app.get("/api/prranks")
def prranks(year: int, top: int = 300):
    """Ranked node ids (most influential first) by GAE PageRank at the anchor year nearest <year> —
    powers the Top-N PageRank filter (client keeps the top-N as a visibility mask)."""
    anchor = min(ANCHORS, key=lambda a: abs(a - year))
    ids = aql(f"""FOR r IN gae_pr_{anchor} SORT r.rank DESC LIMIT @top
                   RETURN CONTAINS(r.id, '/') ? r.id : CONCAT('Node/', r.id)""", {"top": top})
    return {"anchor": anchor, "ids": ids}


@app.get("/api/influence")
def influence(year: int, top: int = 15):
    """Top entities by GAE PageRank at the anchor year nearest <year>."""
    anchor = min(ANCHORS, key=lambda a: abs(a - year))
    rows = aql(f"""FOR r IN gae_pr_{anchor} SORT r.rank DESC LIMIT @top
          LET n = DOCUMENT(CONTAINS(r.id, '/') ? r.id : CONCAT('Node/', r.id))
          RETURN {{name: n.name, type: n.type, rank: r.rank}}""", {"top": top})
    return {"anchor": anchor, "rows": rows}


@app.get("/api/diff")
def diff(ticker: str, frm: int = Query(..., alias="from"), to: int = 2024, limit: int = 40):
    """Facts that appeared / disappeared for a company between two years (by fact identity)."""
    ta, tb = frm * 100 + 6, to * 100 + 6

    def side(anchor_t, other_t):
        return aql("""
            LET other = (FOR e IN relations FILTER e.ticker==@tk AND e.validFrom<=@ot AND e.validTo>@ot
                          RETURN CONCAT(e._from,'|',e.type,'|',e._to))
            FOR e IN relations FILTER e.ticker==@tk AND e.validFrom<=@at AND e.validTo>@at
              AND CONCAT(e._from,'|',e.type,'|',e._to) NOT IN other
              LET df=DOCUMENT(e._from) LET dt=DOCUMENT(e._to)
              FILTER df.isJunkPlaceholder!=true AND dt.isJunkPlaceholder!=true
              LIMIT @lim RETURN {from: df.name, rel: e.type, to: dt.name}""",
            {"tk": ticker, "at": anchor_t, "ot": other_t, "lim": limit})

    return {"ticker": ticker, "from": frm, "to": to,
            "appeared": side(tb, ta), "disappeared": side(ta, tb)}


@app.get("/api/backward")
def backward(ticker: str, lag: int = 3, limit: int = 25):
    """Backward-looking disclosures: facts a filing asserts about periods >= lag years earlier."""
    return aql("""
        FOR e IN relations
          FILTER e.ticker==@tk AND e.startDate!=null
            AND (e.year - TO_NUMBER(SUBSTRING(e.startDate,0,4))) >= @lag
          SORT (e.year - TO_NUMBER(SUBSTRING(e.startDate,0,4))) DESC
          LIMIT @lim
          LET df=DOCUMENT(e._from) LET dt=DOCUMENT(e._to)
          RETURN {filed: e.year, period: e.startDate, from: df.name, rel: e.type, to: dt.name}""",
        {"tk": ticker, "lag": lag, "lim": limit})


@app.get("/health")
def health():
    """Liveness probe for Container Manager. Does not touch Arango."""
    return {
        "status": "ok",
        "database": database(),
        "endpoint_configured": bool(endpoint()),
    }


app.mount("/", StaticFiles(directory=str(_DIR / "static"), html=True))

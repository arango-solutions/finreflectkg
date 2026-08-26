"""Stdlib Arango REST client for the time-travel demo.

Resolves the endpoint and credentials the same way locally (`.env` Basic auth)
and inside Arango Container Manager (injected `ARANGO_DEPLOYMENT_ENDPOINT` +
JWT). No dependency on `scripts/arango.py`, so the BYOC tarball is self-contained.
"""
from __future__ import annotations

import base64
import json
import os
import pathlib
import ssl
import urllib.error
import urllib.request
from contextvars import ContextVar

_HERE = pathlib.Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent

# JWT forwarded by the platform proxy on each inbound request (set by middleware).
request_token: ContextVar[str | None] = ContextVar("request_token", default=None)

_DEFAULT_DB = "FinReflectKgTemporal"


def load_env(path: pathlib.Path | None = None) -> dict[str, str]:
    """Load KEY=VAL pairs from a .env file if present; env vars win for ARANGO_*."""
    env: dict[str, str] = {}
    candidates = []
    if path is not None:
        candidates.append(path)
    else:
        candidates.extend((_HERE / ".env", _REPO_ROOT / ".env", pathlib.Path.cwd() / ".env"))
    seen: set[pathlib.Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved in seen or not candidate.is_file():
            continue
        seen.add(resolved)
        try:
            text = candidate.read_text()
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            val = val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                val = val[1:-1]
            env[key.strip()] = val
    for key, val in os.environ.items():
        if key.startswith("ARANGO_") or key in ("HUGGINGFACE_DATASET", "db_name"):
            env[key] = val
    return env


def endpoint(env: dict[str, str] | None = None) -> str | None:
    """Cluster-internal URL on BYOC; `.env` `ARANGO_ENDPOINT` locally."""
    env = env if env is not None else load_env()
    raw = env.get("ARANGO_DEPLOYMENT_ENDPOINT") or env.get("ARANGO_ENDPOINT")
    if not raw:
        return None
    return raw.rstrip("/")


def database(env: dict[str, str] | None = None) -> str:
    env = env if env is not None else load_env()
    return env.get("ARANGO_DB") or env.get("db_name") or _DEFAULT_DB


def _token_from_env(env: dict[str, str]) -> str | None:
    """`ARANGO_TOKEN` is either a JWT string or a path to a token file (sidecar)."""
    raw = env.get("ARANGO_TOKEN")
    if not raw:
        return None
    path = pathlib.Path(raw)
    if path.is_file():
        try:
            return path.read_text().strip() or None
        except OSError:
            return None
    return raw.strip() or None


def authorization(env: dict[str, str] | None = None) -> str | None:
    """Return a full `Authorization` header value, or None if nothing is configured.

    Preference: inbound request JWT → `ARANGO_TOKEN` → Basic from user/password.
    """
    env = env if env is not None else load_env()
    inbound = request_token.get()
    if inbound:
        return f"bearer {inbound}"
    file_or_env = _token_from_env(env)
    if file_or_env:
        return f"bearer {file_or_env}"
    user = env.get("ARANGO_USER", "")
    password = env.get("ARANGO_PASSWORD", "")
    if user:
        tok = base64.b64encode(f"{user}:{password}".encode()).decode()
        return f"Basic {tok}"
    return None


def _ssl_context(env: dict[str, str]) -> ssl.SSLContext | None:
    # Internal BYOC endpoints often present the cluster's private CA. Skip
    # verification there unless the operator explicitly opted in.
    if env.get("ARANGO_DEPLOYMENT_ENDPOINT") and "ARANGO_VERIFY_SSL" not in os.environ:
        verify = False
    else:
        verify = env.get("ARANGO_VERIFY_SSL", "true").lower() == "true"
    if verify:
        return None
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def parse_bearer(header: str | None) -> str | None:
    """Extract the token from `Authorization: Bearer …` (or a raw token)."""
    if not header:
        return None
    stripped = header.strip()
    for prefix in ("Bearer ", "bearer "):
        if stripped.startswith(prefix):
            stripped = stripped[len(prefix):]
            break
    return stripped.strip() or None


def req(method: str, path: str, body=None, db: str | None = None, timeout: int = 120):
    """Call the ArangoDB REST API. `path` starts with /_api/...; `db` scopes it.

    Returns `(status, body_dict)` — never raises for HTTP/URL errors, matching
    `scripts/arango.py` so the demo's `aql()` helper can map them to 502s.
    """
    env = load_env()
    ep = endpoint(env)
    if not ep:
        return 503, {"errorMessage": "ARANGO_DEPLOYMENT_ENDPOINT or ARANGO_ENDPOINT is not set"}
    auth = authorization(env)
    if not auth:
        return 401, {"errorMessage": "no Arango credentials (request JWT, ARANGO_TOKEN, or ARANGO_USER)"}
    base = f"{ep}/_db/{db}" if db else ep
    url = base + path
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    request.add_header("Authorization", auth)
    try:
        with urllib.request.urlopen(request, context=_ssl_context(env), timeout=timeout) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read() or b"{}")
        except json.JSONDecodeError:
            payload = {"errorMessage": e.reason}
        return e.code, payload
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        return 502, {"errorMessage": str(reason)}
    except TimeoutError:
        return 504, {"errorMessage": "timed out talking to ArangoDB"}
    except json.JSONDecodeError as e:
        return 502, {"errorMessage": f"non-JSON Arango response: {e}"}

#!/usr/bin/env bash
# Pack the time-travel demo as a Container Manager BYOC .tar.gz.
#
# py12base's /scripts/entrypoint.sh extracts this archive into /project and
# then:  ENTRYPOINT=$(cat entrypoint); exec python $ENTRYPOINT
# Layout matches ServiceMaker zipper.sh:
#   entrypoint          # text file: /project/finreflectkg-demo/main.py
#   the_venv/           # manylinux py3.12 wheels (FastAPI is NOT on py12base)
#   finreflectkg-demo/  # source
#
# Usage:
#   ./scripts/package_byoc.sh
#   # writes dist/finreflectkg-demo.tar.gz
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAME="finreflectkg-demo"
STAGE="${ROOT}/dist/${NAME}"
VENV_STAGE="${ROOT}/dist/the_venv"
SITE="${VENV_STAGE}/lib/python3.12/site-packages"
OUT="${ROOT}/dist/${NAME}.tar.gz"
DEMO="${ROOT}/demo"
UV="${UV:-uv}"
PY="${PY:-${ROOT}/.venv/bin/python}"
[[ -x "$PY" ]] || PY="python3"

if ! command -v "$UV" >/dev/null 2>&1; then
  echo "error: uv is required to vendor Linux 3.12 wheels (py12base has no pip)." >&2
  echo "       install: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  exit 1
fi

rm -rf "$STAGE" "$VENV_STAGE"
mkdir -p "$STAGE/static" "$SITE"

install -m 0644 "$DEMO/pyproject.toml" "$STAGE/pyproject.toml"
install -m 0755 "$DEMO/main.py" "$STAGE/main.py"
install -m 0644 "$DEMO/api.py" "$STAGE/api.py"
install -m 0644 "$DEMO/arango_client.py" "$STAGE/arango_client.py"

# Static UI + vendored Cytoscape. Do not copy tests, screenshots, or caches.
# cp -R with trailing /. so we copy the *contents* of static/ (macOS cp -R
# otherwise nests static/static when the dest already exists).
cp -R "$DEMO/static/." "$STAGE/static/"

for required in \
  "$STAGE/pyproject.toml" \
  "$STAGE/main.py" \
  "$STAGE/api.py" \
  "$STAGE/arango_client.py" \
  "$STAGE/static/index.html" \
  "$STAGE/static/app.js" \
  "$STAGE/static/style.css" \
  "$STAGE/static/vendor/cytoscape.min.js"
do
  if [[ ! -f "$required" ]]; then
    echo "error: missing $required" >&2
    exit 1
  fi
done

if [[ -f "$STAGE/.env" ]]; then
  echo "error: .env must not be packed into the BYOC archive" >&2
  exit 1
fi

# py12base is CPython 3.12 on linux/amd64 and has no pip. Cross-compile wheels
# into the_venv so entrypoint.sh's PYTHONPATH=/project/the_venv/lib/python*/site-packages
# can import FastAPI without touching PyPI at runtime.
echo "vendoring manylinux x86_64 / cp312 wheels into the_venv ..."
"$UV" pip install \
  --target "$SITE" \
  --python-version 3.12 \
  --python-platform x86_64-manylinux_2_17 \
  --no-compile \
  -r "$DEMO/pyproject.toml"
if [[ ! -d "$SITE/fastapi" || ! -d "$SITE/uvicorn" ]]; then
  echo "error: uv did not install fastapi/uvicorn into $SITE" >&2
  exit 1
fi

# Absolute path the py12base image will `exec python`.
printf '%s\n' "/project/${NAME}/main.py" > "${ROOT}/dist/entrypoint"

# Python tarfile: GNU long names, no macOS xattr pax headers.
export COPYFILE_DISABLE=1
"$PY" - "$OUT" "$ROOT/dist" "$NAME" <<'PY'
import sys
import tarfile
from pathlib import Path

out, dist, name = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
members = ["entrypoint", "the_venv", name]

def filt(info: tarfile.TarInfo):
    parts = Path(info.name).parts
    if "__pycache__" in parts or info.name.endswith((".pyc", ".pyo")):
        return None
    info.uid = info.gid = 0
    info.uname = info.gname = "user"
    return info

with tarfile.open(out, "w:gz", format=tarfile.GNU_FORMAT, compresslevel=6) as tar:
    for member in members:
        src = dist / member
        if not src.exists():
            raise SystemExit(f"missing {src}")
        tar.add(src, arcname=member, filter=filt)
print(f"packed {', '.join(members)}")
PY

echo "wrote $OUT ($(wc -c < "$OUT" | tr -d ' ') bytes)"
echo "layout: entrypoint + the_venv (cp312 manylinux) + ${NAME}/"
echo "upload: Control Panel → Container Manager → Packages → ${NAME}.tar.gz"
echo "deploy: base image py12base, path e.g. finreflect, scope = FinReflectKgTemporal"

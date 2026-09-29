#!/usr/bin/env bash
# Build the BYOC bundle for the Arango platform.
#
# Output: a FLAT tar.gz — `entrypoint` and `requirements.txt` at the archive root,
# with demo/ and scripts/ beside them. Flat is the platform contract: the Container
# Manager unpacks into /project and runs `python /project/<entrypoint>`.
#
# The previous version of this script produced a WRAPPED archive (everything under
# finreflectkg-timetravel/) built against the container-image contract. That shape
# will not boot as a platform package — it is kept as package.sh.wrapped-contract.bak
# only for reference.
#
#   ./deploy/package.sh 1.0.0                 # no credentials — will not boot on the platform
#   ./deploy/package.sh 1.0.0 --with-env      # bakes .env — THE ARCHIVE IS SECRET
#
# --with-env is required to deploy: the platform injects no environment, so the
# service reads the baked .env. *.tar.gz is gitignored for exactly this reason.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAME="finreflectkg-timetravel"
VERSION="${1:?usage: package.sh <version> [--with-env]}"
WITH_ENV=0; [ "${2:-}" = "--with-env" ] && WITH_ENV=1
OUT="${PACKAGE_OUT:-$REPO/target}"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

# The service reads FinReflectKgTemporal (hardcoded in demo/api.py), NOT the repo's
# ARANGO_DB. The mount path's <db> segment must name a database that exists on the
# target cluster, so derive it from the app rather than from .env — which currently
# says FinReflectKG, a database that does not exist on prod.demo.
DB="$(grep -E '^DB = ' "$REPO/demo/api.py" | head -1 | sed -E 's/.*"([^"]+)".*/\1/')"
DB="${DB:-FinReflectKgTemporal}"
INSTANCE="${INSTANCE:-finreflect}"
PREFIX="/_service/uds/_db/${DB}/${INSTANCE}"

mkdir -p "$OUT" "$STAGE/demo" "$STAGE/scripts"
cp "$REPO/deploy/entrypoint" "$STAGE/entrypoint"; chmod +x "$STAGE/entrypoint"
head -1 "$STAGE/entrypoint" | grep -q '^entrypoint' \
  || { echo "error: entrypoint line 1 must start with 'entrypoint'" >&2; exit 1; }
cp "$REPO/deploy/requirements.txt" "$STAGE/requirements.txt"
cp -R "$REPO/demo/." "$STAGE/demo/"
# demo/api.py imports scripts/arango.py as a SIBLING (sys.path.insert on ../scripts).
# Flattening that away breaks it at import time, not at build time.
cp "$REPO/scripts/arango.py" "$STAGE/scripts/arango.py"

find "$STAGE" \( -name '__pycache__' -o -name '*.pyc' -o -name '.DS_Store' \
  -o -name '.env' -o -name '*.env' -o -name '*.bak' \) -exec rm -rf {} + 2>/dev/null || true

if [ "$WITH_ENV" -eq 1 ]; then
  [ -f "$REPO/.env" ] || { echo "error: --with-env but no .env at the repo root" >&2; exit 1; }
  # Only what the SERVICE needs. The repo .env also holds OpenAI / OpenRouter keys for
  # the NL toolchain, and the UI imports none of it — baking them would put two
  # unnecessary secrets into a distributable artifact.
  grep -E '^ARANGO_(ENDPOINT|USER|PASSWORD|DATABASE|VERIFY_SSL)=' "$REPO/.env" > "$STAGE/.env"
  # demo/prefix.py strips this before routing. It must match the mount path
  # the deploy tool computes (scripts/byoc-deploy), or every request 404s.
  echo "SERVICE_URL_PATH_PREFIX=${PREFIX}" >> "$STAGE/.env"
fi

tar -czf "$OUT/$NAME-$VERSION.tar.gz" -C "$STAGE" .

echo "✓ $OUT/$NAME-$VERSION.tar.gz  ($(du -h "$OUT/$NAME-$VERSION.tar.gz" | cut -f1))"
echo "  mount prefix : $PREFIX"
echo "  credentials  : $([ "$WITH_ENV" -eq 1 ] && echo 'BAKED IN — treat as a secret' || echo 'absent (will not boot on the platform)')"
echo "  root entries : $(tar -tzf "$OUT/$NAME-$VERSION.tar.gz" | sed 's|^\./||' | awk -F/ 'NF&&$1!=""{print $1}' | sort -u | tr '\n' ' ')"

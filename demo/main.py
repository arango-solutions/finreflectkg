#!/usr/bin/env python
"""BYOC entrypoint — HTTP on 0.0.0.0:8000 as required by Container Manager.

The py12base image's /scripts/entrypoint.sh extracts the uploaded tarball into
/project, reads the path in /project/entrypoint, and `exec python`s that file.
This module is that file.

FastAPI is not on py12base (only python-arango/networkx). Extra deps are
shipped in the tarball at the_venv/lib/python3.12/site-packages, which
entrypoint.sh puts on PYTHONPATH. We also prepend that path here in case the
shell glob did not match.

Local equivalent:  python demo/main.py   then open http://localhost:8000
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))


def bundled_site_packages() -> list[Path]:
    """site-packages dirs shipped next to the project (ServiceMaker the_venv)."""
    roots = (
        Path("/project/the_venv"),
        _DIR.parent / "the_venv",
        _DIR / "the_venv",
    )
    found: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for p in sorted(root.glob("lib/python*/site-packages")):
            resolved = p.resolve()
            if resolved not in seen:
                seen.add(resolved)
                found.append(p)
    return found


def _prepend_bundled_site_packages() -> None:
    for p in reversed(bundled_site_packages()):
        s = str(p)
        if s in sys.path:
            sys.path.remove(s)
        sys.path.insert(0, s)


def _ensure_deps() -> None:
    """Make FastAPI importable from the tarball's the_venv. Do not pip-install.

    py12base's venv has no pip module; runtime `python -m pip` fails with
    "No module named pip". Dependencies must be packed as manylinux wheels.
    """
    _prepend_bundled_site_packages()
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
    except ImportError as exc:
        bundled = [str(p) for p in bundled_site_packages()]
        raise RuntimeError(
            "fastapi/uvicorn are not importable. The BYOC tarball must include "
            "the_venv/lib/python3.12/site-packages (rebuild with "
            "./scripts/package_byoc.sh). "
            f"bundled={bundled or 'none'} sys.path[0:5]={sys.path[:5]!r}"
        ) from exc


_ensure_deps()
from api import app  # noqa: E402


def main() -> None:
    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()

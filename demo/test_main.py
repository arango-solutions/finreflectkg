"""Tests for demo/main.py BYOC bootstrap."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import main as demo_main  # noqa: E402


class BundledSitePackagesTests(unittest.TestCase):
    def test_discovers_the_venv_next_to_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "the_venv" / "lib" / "python3.12" / "site-packages"
            site.mkdir(parents=True)
            with patch.object(demo_main, "_DIR", Path(tmp) / "finreflectkg-demo"):
                found = demo_main.bundled_site_packages()
        self.assertEqual(found, [site])

    def test_prepend_puts_bundled_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp) / "the_venv" / "lib" / "python3.12" / "site-packages"
            site.mkdir(parents=True)
            with patch.object(demo_main, "_DIR", Path(tmp) / "finreflectkg-demo"):
                demo_main._prepend_bundled_site_packages()
        self.assertEqual(sys.path[0], str(site))
        # cleanup so later tests don't keep the fake path
        if sys.path[0] == str(site):
            sys.path.pop(0)


class EnsureDepsTests(unittest.TestCase):
    def test_noop_when_fastapi_and_uvicorn_present(self):
        demo_main._ensure_deps()  # must not raise

    def test_raises_without_trying_pip_when_missing(self):
        real_import = __import__

        def fake_import(name, *args, **kwargs):
            if name in ("fastapi", "uvicorn"):
                raise ImportError(name)
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            with self.assertRaises(RuntimeError) as ctx:
                demo_main._ensure_deps()
        self.assertIn("package_byoc.sh", str(ctx.exception))
        self.assertNotIn("pip", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()

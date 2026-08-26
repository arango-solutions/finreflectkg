"""Assert the BYOC packaging script produces a deployable archive."""
from __future__ import annotations

import subprocess
import tarfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "package_byoc.sh"
ARCHIVE = ROOT / "dist" / "finreflectkg-demo.tar.gz"

REQUIRED = {
    "entrypoint",
    "the_venv/lib/python3.12/site-packages/fastapi",
    "the_venv/lib/python3.12/site-packages/uvicorn",
    "finreflectkg-demo/pyproject.toml",
    "finreflectkg-demo/main.py",
    "finreflectkg-demo/api.py",
    "finreflectkg-demo/arango_client.py",
    "finreflectkg-demo/static/index.html",
    "finreflectkg-demo/static/app.js",
    "finreflectkg-demo/static/style.css",
    "finreflectkg-demo/static/vendor/cytoscape.min.js",
}

FORBIDDEN_SUFFIXES = (
    "test_api.py",
    "test_arango_client.py",
    "test_package_byoc.py",
    "test_main.py",
    ".env",
    "screenshot.sh",
)


class PackageByocTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run([str(SCRIPT)], check=True, cwd=str(ROOT))

    def test_archive_exists(self):
        self.assertTrue(ARCHIVE.is_file())
        # Source + vendored manylinux wheels is well above the old ~130 KB.
        self.assertGreater(ARCHIVE.stat().st_size, 500_000)

    def test_venv_wheels_are_linux_x86_64(self):
        with tarfile.open(ARCHIVE, "r:gz") as tar:
            names = tar.getnames()
        linux_ext = [n for n in names if n.endswith("x86_64-linux-gnu.so")]
        self.assertTrue(linux_ext, msg="expected cp312 manylinux .so files in the_venv")
        macos_ext = [n for n in names if "darwin" in n or n.endswith(".dylib")]
        self.assertFalse(macos_ext)

    def test_archive_contains_service_and_excludes_tests_and_secrets(self):
        with tarfile.open(ARCHIVE, "r:gz") as tar:
            names = tar.getnames()
        self.assertTrue(set(REQUIRED).issubset(set(names)), msg=sorted(REQUIRED - set(names)))
        joined = "\n".join(names)
        for suffix in FORBIDDEN_SUFFIXES:
            self.assertNotIn(suffix, joined)
        # pyproject pins the BYOC runtime
        with tarfile.open(ARCHIVE, "r:gz") as tar:
            text = tar.extractfile("finreflectkg-demo/pyproject.toml").read().decode()
        self.assertIn('requires-python = ">=3.12"', text)
        self.assertIn("fastapi", text)
        with tarfile.open(ARCHIVE, "r:gz") as tar:
            main = tar.extractfile("finreflectkg-demo/main.py").read().decode()
        self.assertIn('"8000"', main)
        self.assertIn('"0.0.0.0"', main)
        self.assertIn("uvicorn.run", main)

    def test_entrypoint_is_top_level_path_file(self):
        """py12base does: ENTRYPOINT=$(cat entrypoint); exec python $ENTRYPOINT."""
        with tarfile.open(ARCHIVE, "r:gz") as tar:
            names = tar.getnames()
            info = tar.getmember("entrypoint")
            self.assertTrue(info.isfile())
            path = tar.extractfile("entrypoint").read().decode().strip()
        self.assertIn("entrypoint", names)
        self.assertNotIn("finreflectkg-demo/entrypoint", names)
        self.assertEqual(path, "/project/finreflectkg-demo/main.py")

    def test_no_macos_xattr_headers(self):
        with tarfile.open(ARCHIVE, "r:gz") as tar:
            for member in tar.getmembers():
                self.assertFalse(member.name.startswith("._"), msg=member.name)
                keys = " ".join(member.pax_headers)
                self.assertNotIn("LIBARCHIVE.xattr", keys, msg=member.name)


if __name__ == "__main__":
    unittest.main()

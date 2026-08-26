"""HTTP-level tests for the demo FastAPI app (no live Arango)."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient

from api import app
from arango_client import request_token


class DemoAppTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        request_token.set(None)

    def test_health_does_not_need_arango(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertIn("database", body)
        self.assertIn("endpoint_configured", body)

    def test_health_reports_arango_db_from_env(self):
        with patch.dict(os.environ, {"ARANGO_DB": "OtherDb"}, clear=False):
            r = self.client.get("/health")
        self.assertEqual(r.json()["database"], "OtherDb")

    def test_years_is_static(self):
        r = self.client.get("/api/years")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["min"], 2014)
        self.assertEqual(body["max"], 2024)
        self.assertEqual(body["anchors"], [2014, 2019, 2020, 2024])

    def test_root_serves_html(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/html", r.headers["content-type"])
        self.assertIn("FinReflectKG", r.text)
        self.assertIn('href="style.css"', r.text)
        self.assertNotIn('href="/style.css"', r.text)

    def test_static_css_and_js(self):
        css = self.client.get("/style.css")
        self.assertEqual(css.status_code, 200)
        js = self.client.get("/app.js")
        self.assertEqual(js.status_code, 200)
        self.assertIn("serviceBase", js.text)

    def test_tickers_without_endpoint_is_502(self):
        with patch("api.req", return_value=(503, {"errorMessage": "no endpoint"})):
            r = self.client.get("/api/tickers")
        self.assertEqual(r.status_code, 502)
        self.assertIn("no endpoint", r.json()["detail"])

    def test_inbound_bearer_is_bound_for_aql(self):
        captured = {}

        def fake_req(method, path, body=None, db=None, timeout=120):
            captured["token"] = request_token.get()
            captured["db"] = db
            return 200, {"result": ["aapl"], "hasMore": False}

        with patch("api.req", side_effect=fake_req):
            r = self.client.get(
                "/api/tickers", headers={"Authorization": "Bearer inbound-jwt"}
            )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), ["aapl"])
        self.assertEqual(captured["token"], "inbound-jwt")
        self.assertTrue(captured["db"])


class FrontendPrefixTests(unittest.TestCase):
    """The UI must not use origin-absolute /api or /asset paths (BYOC prefix)."""

    def test_index_assets_are_relative(self):
        html = Path(__file__).resolve().parent / "static" / "index.html"
        text = html.read_text(encoding="utf-8")
        self.assertNotIn('href="/style.css"', text)
        self.assertNotIn('src="/app.js"', text)
        self.assertNotIn('src="/vendor/', text)
        self.assertIn('href="style.css"', text)
        self.assertIn('src="app.js"', text)

    def test_app_js_fetches_are_relative(self):
        js = (Path(__file__).resolve().parent / "static" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("j('/api/", js)
        self.assertNotIn('j("/api/', js)
        self.assertIn("serviceBase", js)
        self.assertIn("credentials: 'same-origin'", js)


if __name__ == "__main__":
    unittest.main()

"""Tests for demo/arango_client.py — local .env vs BYOC JWT resolution."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import urllib.error
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from arango_client import (
    authorization,
    database,
    endpoint,
    load_env,
    parse_bearer,
    req,
    request_token,
)


class LoadEnvTests(unittest.TestCase):
    def test_missing_file_does_not_raise(self):
        env = load_env(Path("/no/such/.env"))
        self.assertIsInstance(env, dict)

    def test_parses_quotes_and_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / ".env"
            p.write_text(
                '# ignore\nARANGO_ENDPOINT="https://db.example:8529"\nARANGO_USER=root\n\n'
            )
            env = load_env(p)
        self.assertEqual(env["ARANGO_ENDPOINT"], "https://db.example:8529")
        self.assertEqual(env["ARANGO_USER"], "root")

    def test_environ_overrides_file_for_arango_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / ".env"
            p.write_text("ARANGO_DB=fromfile\n")
            with patch.dict(os.environ, {"ARANGO_DB": "fromenv"}, clear=False):
                env = load_env(p)
        self.assertEqual(env["ARANGO_DB"], "fromenv")


class EndpointDatabaseTests(unittest.TestCase):
    def test_deployment_endpoint_wins_over_local(self):
        env = {
            "ARANGO_DEPLOYMENT_ENDPOINT": "https://internal:8529/",
            "ARANGO_ENDPOINT": "https://external:8529",
        }
        self.assertEqual(endpoint(env), "https://internal:8529")

    def test_missing_endpoint_is_none(self):
        self.assertIsNone(endpoint({}))

    def test_database_prefers_arango_db_then_db_name(self):
        self.assertEqual(database({"ARANGO_DB": "A", "db_name": "B"}), "A")
        self.assertEqual(database({"db_name": "B"}), "B")
        self.assertEqual(database({}), "FinReflectKgTemporal")


class AuthorizationTests(unittest.TestCase):
    def tearDown(self):
        request_token.set(None)

    def test_parse_bearer_strips_prefix(self):
        self.assertEqual(parse_bearer("Bearer abc.def"), "abc.def")
        self.assertEqual(parse_bearer("bearer xyz"), "xyz")
        self.assertEqual(parse_bearer("raw-token"), "raw-token")
        self.assertIsNone(parse_bearer(None))
        self.assertIsNone(parse_bearer("   "))

    def test_request_jwt_wins_over_basic(self):
        request_token.set("inbound-jwt")
        header = authorization({"ARANGO_USER": "root", "ARANGO_PASSWORD": "x"})
        self.assertEqual(header, "bearer inbound-jwt")

    def test_token_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "token"
            p.write_text("file-jwt\n")
            header = authorization({"ARANGO_TOKEN": str(p)})
        self.assertEqual(header, "bearer file-jwt")

    def test_token_string_when_not_a_file(self):
        header = authorization({"ARANGO_TOKEN": "env-jwt"})
        self.assertEqual(header, "bearer env-jwt")

    def test_basic_fallback(self):
        header = authorization({"ARANGO_USER": "root", "ARANGO_PASSWORD": "s3cret"})
        self.assertTrue(header.startswith("Basic "))
        # root:s3cret
        self.assertIn("cm9vdDpzM2NyZXQ=", header)

    def test_no_credentials_is_none(self):
        self.assertIsNone(authorization({}))


class ReqTests(unittest.TestCase):
    def tearDown(self):
        request_token.set(None)

    def test_missing_endpoint_is_503(self):
        with patch("arango_client.load_env", return_value={}):
            st, body = req("GET", "/_api/version")
        self.assertEqual(st, 503)
        self.assertIn("ENDPOINT", body["errorMessage"])

    def test_missing_credentials_is_401(self):
        with patch(
            "arango_client.load_env",
            return_value={"ARANGO_ENDPOINT": "https://db.example:8529"},
        ):
            st, body = req("GET", "/_api/version")
        self.assertEqual(st, 401)

    def test_http_error_returns_status_and_body(self):
        err = urllib.error.HTTPError(
            "https://db.example:8529/_api/cursor",
            404,
            "not found",
            hdrs={},
            fp=BytesIO(b'{"errorMessage":"unknown collection"}'),
        )
        with patch("arango_client.load_env", return_value={
            "ARANGO_ENDPOINT": "https://db.example:8529",
            "ARANGO_USER": "root",
        }), patch("urllib.request.urlopen", side_effect=err):
            st, body = req("POST", "/_api/cursor", {"query": "RETURN 1"}, db="kg")
        self.assertEqual(st, 404)
        self.assertEqual(body["errorMessage"], "unknown collection")

    def test_success_posts_json_with_basic_auth(self):
        payload = {"result": [1], "hasMore": False}
        resp = MagicMock()
        resp.status = 201
        resp.read.return_value = json.dumps(payload).encode()
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        with patch("arango_client.load_env", return_value={
            "ARANGO_ENDPOINT": "https://db.example:8529",
            "ARANGO_USER": "root",
            "ARANGO_PASSWORD": "x",
        }), patch("urllib.request.urlopen", return_value=resp) as opener:
            st, body = req("POST", "/_api/cursor", {"query": "RETURN 1"}, db="kg")
        self.assertEqual(st, 201)
        self.assertEqual(body["result"], [1])
        call_req = opener.call_args[0][0]
        self.assertIn("/_db/kg/_api/cursor", call_req.full_url)
        self.assertTrue(call_req.get_header("Authorization").startswith("Basic "))


if __name__ == "__main__":
    unittest.main()

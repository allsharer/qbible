"""HTTP API and local-service security tests (real server on a free loopback port)."""

import http.client
import json
import threading
import unittest

from qbible.errors import QBibleError
from qbible.paths import locations
from qbible.server import SECURITY_HEADERS, create_server
from qbible.services import BibleService

from .helpers import IsolatedEnv, require_kjv


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        require_kjv()
        cls.env = IsolatedEnv().__enter__()
        locs = locations()
        cls.service = BibleService.from_environment(locs)
        cls.httpd = create_server(cls.service, locs.web, "127.0.0.1", 0)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.env.__exit__(None, None, None)

    def req(self, method, path, body=None, headers=None, host=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Host": host or f"127.0.0.1:{self.port}"}
        h.update(headers or {})
        data = None
        if body is not None:
            data = json.dumps(body).encode() if not isinstance(body, bytes) else body
        conn.request(method, path, body=data, headers=h)
        r = conn.getresponse()
        raw = r.read()
        conn.close()
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = raw
        return r.status, dict(r.getheaders()), payload

    def post(self, path, body, **extra):
        headers = {"Content-Type": "application/json", "X-QBible-Request": "1"}
        headers.update(extra)
        return self.req("POST", path, body, headers)

    # -- API ----------------------------------------------------------------------
    def test_info_and_translations(self):
        s, _, d = self.req("GET", "/api/v1/info")
        self.assertEqual((s, d["api_version"], d["default_translation"]), (200, 1, "kjv"))
        s, _, d = self.req("GET", "/api/v1/translations")
        self.assertEqual(d["translations"][0]["id"], "kjv")
        s, _, d = self.req("GET", "/api/v1/translations/kjv/books")
        self.assertEqual(len(d["books"]), 66)
        self.assertEqual(self.req("GET", "/api/v1/translations/zzz/books")[0], 404)

    def test_passage(self):
        s, _, d = self.req("GET", "/api/v1/passage?ref=Rev%2021:1-4")
        self.assertEqual(s, 200)
        self.assertEqual(d["reference"]["display"], "Revelation 21:1-4")
        self.assertEqual(len(d["chapters"][0]["verses"]), 4)
        self.assertEqual(d["next"]["display"], "Revelation 22")
        s, _, d = self.req("GET", "/api/v1/passage?ref=JHN.3.16")
        self.assertEqual(d["reference"]["display"], "John 3:16")
        v = d["chapters"][0]["verses"][0]
        self.assertTrue(v["paragraph"])
        self.assertNotIn("¶", v["text"])
        s, _, d = self.req("GET", "/api/v1/passage?ref=John%2022")
        self.assertEqual((s, d["error"]["code"]), (400, "invalid_chapter"))
        self.assertEqual(self.req("GET", "/api/v1/passage")[0], 400)

    def test_resolve_and_references(self):
        _, _, d = self.req("GET", "/api/v1/resolve?q=1%20cor%2013:4-7")
        self.assertEqual(d["match"]["key"], "1CO.13.4-1CO.13.7")
        _, _, d = self.req("GET", "/api/v1/resolve?q=faith%20hope")
        self.assertIsNone(d["match"])
        _, _, d = self.req("GET", "/api/v1/references?text=see%20Romans%208:28%20today")
        self.assertEqual([r["display"] for r in d["references"]], ["Romans 8:28"])

    def test_search(self):
        s, _, d = self.req("GET", "/api/v1/search?q=%22fear%20not%22&limit=5&offset=5")
        self.assertEqual(s, 200)
        self.assertEqual(len(d["results"]), 5)
        self.assertTrue(d["has_more"])
        self.assertEqual(d["offset"], 5)
        s, _, d = self.req("GET", "/api/v1/search?q=")
        self.assertEqual(s, 400)
        s, _, d = self.req("GET", "/api/v1/search?q=love&limit=abc")
        self.assertEqual(s, 400)
        s, _, d = self.req("GET", "/api/v1/search?q=%27%3B%20DROP%20TABLE%20verses%3B--")
        self.assertEqual(s, 200)

    def test_unknown_endpoint(self):
        self.assertEqual(self.req("GET", "/api/v1/nope")[0], 404)
        self.assertEqual(self.req("GET", "/api/v2/info")[0], 404)

    # -- user data -----------------------------------------------------------------
    def test_bookmark_and_history_api(self):
        s, _, d = self.post("/api/v1/user/bookmarks", {"translation": "kjv", "ref": "Psalm 23", "label": "Shepherd"})
        self.assertEqual(s, 200)
        self.assertTrue(d["created"])
        bid = d["bookmark"]["id"]
        s, _, d = self.post("/api/v1/user/bookmarks", {"ref": "PSA.23"})
        self.assertFalse(d["created"])
        s, _, d = self.req("GET", "/api/v1/user/bookmarks")
        self.assertIn("Psalm 23", [b["reference"] for b in d["bookmarks"]])
        s, _, d = self.post("/api/v1/user/bookmarks", {"ref": "John 99:1"})
        self.assertEqual(s, 400)
        s, _, _ = self.req("DELETE", f"/api/v1/user/bookmarks/{bid}", headers={"X-QBible-Request": "1"})
        self.assertEqual(s, 200)
        s, _, _ = self.req("DELETE", f"/api/v1/user/bookmarks/{bid}", headers={"X-QBible-Request": "1"})
        self.assertEqual(s, 404)
        self.assertEqual(self.post("/api/v1/user/history", {"ref": "John 1"})[0], 200)
        _, _, d = self.req("GET", "/api/v1/user/history")
        self.assertEqual(d["history"][0]["reference"], "John 1")

    def test_csrf_protections(self):
        body = {"ref": "John 1"}
        # no custom header
        self.assertEqual(self.req("POST", "/api/v1/user/bookmarks", body, {"Content-Type": "application/json"})[0], 403)
        # simple form post (no preflight) is refused
        self.assertEqual(self.req("POST", "/api/v1/user/bookmarks", b"ref=John+1",
                                  {"Content-Type": "application/x-www-form-urlencoded", "X-QBible-Request": "1"})[0], 403)
        # cross-origin
        self.assertEqual(self.post("/api/v1/user/bookmarks", body, Origin="https://evil.example")[0], 403)
        self.assertEqual(self.req("DELETE", "/api/v1/user/history")[0], 403)
        # no CORS headers are ever sent
        _, h, _ = self.req("OPTIONS", "/api/v1/user/bookmarks", headers={"Origin": "https://evil.example"})
        self.assertNotIn("Access-Control-Allow-Origin", h)

    def test_body_limits_and_bad_json(self):
        self.assertEqual(self.post("/api/v1/user/bookmarks", b"{not json")[0], 400)
        self.assertEqual(self.post("/api/v1/user/bookmarks", b"[1,2]")[0], 400)
        self.assertEqual(self.post("/api/v1/user/bookmarks", b"x" * 20000)[0], 413)
        self.assertEqual(self.post("/api/v1/user/bookmarks", {"ref": "John 1", "label": "x" * 1000})[0], 400)

    # -- security --------------------------------------------------------------
    def test_dns_rebinding_host_check(self):
        self.assertEqual(self.req("GET", "/api/v1/info", host="evil.example")[0], 421)
        self.assertEqual(self.req("GET", "/api/v1/info", host=f"localhost:{self.port}")[0], 200)

    def test_security_headers(self):
        for path in ["/", "/api/v1/info", "/assets/css/app.css", "/missing"]:
            _, h, _ = self.req("GET", path)
            for k in SECURITY_HEADERS:
                self.assertIn(k, h, f"{k} on {path}")
        _, h, _ = self.req("GET", "/api/v1/user/bookmarks")
        self.assertEqual(h["Cache-Control"], "no-store")

    def test_static_files_and_spa_routes(self):
        for path in ["/", "/bible/kjv/john/3/16", "/search?q=love"]:
            s, h, body = self.req("GET", path)
            self.assertEqual(s, 200)
            self.assertTrue(h["Content-Type"].startswith("text/html"))
        s, h, _ = self.req("GET", "/assets/js/app.js")
        self.assertEqual((s, h["Content-Type"]), (200, "text/javascript; charset=utf-8"))

    def test_path_traversal_blocked(self):
        for path in ["/../qbible/cli.py", "/assets/../../qbible/cli.py", "/%2e%2e/%2e%2e/etc/passwd",
                     "/assets/%2e%2e%2f%2e%2e%2fREADME.md", "/.git/config", "/assets/js/", "/assets%00.js",
                     "/..%5c..%5cetc%5cpasswd"]:
            with self.subTest(path=path):
                s, _, _ = self.req("GET", path)
                self.assertEqual(s, 404)

    def test_no_third_party_assets_in_html(self):
        _, _, html = self.req("GET", "/")
        text = html.decode()
        self.assertNotRegex(text, r"(src|href)=\"https?://")
        self.assertNotIn("<script>", text)  # no inline scripts (CSP)

    def test_refuses_non_loopback_without_flag(self):
        with self.assertRaises(QBibleError):
            create_server(self.service, locations().web, "0.0.0.0", 0)


class DisabledUserDataTests(unittest.TestCase):
    def test_user_endpoints_disabled(self):
        require_kjv()
        with IsolatedEnv():
            locs = locations()
            httpd = create_server(BibleService.from_environment(locs), locs.web, "127.0.0.1", 0, user_data=False)
            t = threading.Thread(target=httpd.serve_forever, daemon=True)
            t.start()
            try:
                port = httpd.server_address[1]
                conn = http.client.HTTPConnection("127.0.0.1", port)
                conn.request("GET", "/api/v1/user/bookmarks")
                r = conn.getresponse()
                self.assertEqual(r.status, 404)
                r.read()
                conn.request("GET", "/api/v1/info")
                self.assertFalse(json.loads(conn.getresponse().read())["user_data"])
                conn.close()
            finally:
                httpd.shutdown()
                httpd.server_close()


if __name__ == "__main__":
    unittest.main()

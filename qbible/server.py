"""Local HTTP server for the browser interface and the versioned JSON API.

Trust boundary and security controls (see docs/DEPLOYMENT.md):

* Binds to 127.0.0.1 by default; any non-loopback address requires
  ``--allow-remote``.
* Host header allow-list on loopback (defends against DNS rebinding).
* State-changing requests require ``Content-Type: application/json`` and an
  ``X-QBible-Request`` header and, when present, a same-origin ``Origin``.
  No CORS headers are sent, so other web sites cannot call the API.
* Strict Content-Security-Policy (no inline script, no third-party origins)
  and other hardening headers on every response.
* Static files are served only from the web asset directory; paths are
  normalised and confined to it.
* Request bodies are limited in size; all inputs are validated by the
  service layer; SQL is parameterised.
* No access log is written by default, so searches and reading history are
  not recorded anywhere except the user's own database.
"""

from __future__ import annotations

import ipaddress
import json
import mimetypes
import posixpath
import signal
import socket
import sys
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from . import __version__
from .errors import (
    DataError,
    NotFoundError,
    QBibleError,
    ReferenceError_,
    SearchQueryError,
    TranslationNotFoundError,
    UserDataError,
)
from .paths import Locations
from .services import BibleService

API_PREFIX = "/api/v1/"
API_VERSION = 1
MAX_BODY = 16 * 1024
SPA_PREFIXES = ("/bible/", "/search")

SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; font-src 'self'; manifest-src 'self'; base-uri 'none'; "
        "form-action 'self'; frame-ancestors 'none'; object-src 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
}

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".webmanifest": "application/manifest+json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".txt": "text/plain; charset=utf-8",
    ".woff2": "font/woff2",
}


class HTTPError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code


def is_loopback(host: str) -> bool:
    if host in ("localhost", "localhost.localdomain"):
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def _int(q: dict, name: str, default: int) -> int:
    v = q.get(name)
    if v is None or v == "":
        return default
    try:
        return int(v)
    except ValueError:
        raise HTTPError(400, "invalid_parameter", f"'{name}' must be a whole number.") from None


class App:
    """Request routing, independent of the HTTP server plumbing (easy to test)."""

    def __init__(self, service: BibleService, web_dir: Path, *, user_data: bool = True,
                 allowed_hosts: set[str] | None = None):
        self.service = service
        self.web_dir = Path(web_dir).resolve()
        self.user_data = user_data
        self.allowed_hosts = allowed_hosts  # None = do not check

    # -- API ---------------------------------------------------------------------
    def api(self, method: str, path: str, query: dict, body: dict | None):
        svc = self.service
        parts = [unquote(p) for p in path[len(API_PREFIX):].split("/") if p]
        t = query.get("t") or query.get("translation") or None
        if t is not None and len(t) > 32:
            raise HTTPError(400, "invalid_parameter", "Invalid translation id.")

        def need(name: str) -> str:
            v = query.get(name)
            if v is None or not v.strip():
                raise HTTPError(400, "missing_parameter", f"The '{name}' parameter is required.")
            return v

        if method == "GET":
            if parts == ["info"]:
                return {
                    "app": "qbible", "version": __version__, "api_version": API_VERSION,
                    "user_data": self.user_data, "default_translation": svc.default_translation,
                }
            if parts == ["translations"]:
                return {"translations": svc.translations(), "default": svc.default_translation}
            if len(parts) == 3 and parts[0] == "translations" and parts[2] == "books":
                return {"translation": parts[1], "books": svc.books(parts[1])}
            if parts == ["passage"]:
                view = svc.passage(need("ref"), t, whole_book_as_first_chapter=True)
                return view.to_dict()
            if parts == ["resolve"]:
                q = need("q")
                try:
                    p = svc.resolve(q, t)
                except ReferenceError_ as e:
                    return {"match": None, "error": {"code": e.code, "message": str(e)}}
                return {"match": {"key": p.key(), "display": p.display(), "book": p.book.to_dict(),
                                  "start": {"chapter": p.start[0], "verse": p.start[1]},
                                  "end": {"chapter": p.end[0], "verse": p.end[1]}}}
            if parts == ["references"]:
                text = need("text")
                if len(text) > 2000:
                    raise HTTPError(400, "invalid_parameter", "Text is too long.")
                return {"references": svc.find_references(text, t)}
            if parts == ["search"]:
                testament = (query.get("testament") or "").upper() or None
                result = svc.search(
                    need("q"), t, mode=query.get("mode") or "auto",
                    limit=_int(query, "limit", 25), offset=_int(query, "offset", 0),
                    sort=query.get("sort") or "canonical", book=query.get("book") or None,
                    testament=testament, context=_int(query, "context", 0),
                )
                return svc.search_dict(result, t)
            if parts == ["random"]:
                testament = (query.get("testament") or "").upper() or None
                if testament not in (None, "OT", "NT"):
                    raise HTTPError(400, "invalid_parameter", "testament must be OT or NT.")
                return svc.random_verse(t, testament).to_dict()

        if parts[:1] == ["user"]:
            if not self.user_data:
                raise HTTPError(404, "user_data_disabled",
                                "Server-side user data is disabled; the browser stores it locally.")
            return self.user_api(method, parts[1:], query, body or {})
        raise HTTPError(404, "not_found", "Unknown API endpoint.")

    def user_api(self, method: str, parts: list[str], query: dict, body: dict):
        svc = self.service
        store = svc.user

        def body_str(name: str, required: bool = True, max_len: int = 200) -> str:
            v = body.get(name, "")
            if not isinstance(v, str) or (required and not v.strip()):
                raise HTTPError(400, "invalid_body", f"'{name}' must be a non-empty string.")
            if len(v) > max_len:
                raise HTTPError(400, "invalid_body", f"'{name}' is too long.")
            return v

        def resolve_body():
            pack = svc.pack(body_str("translation", required=False, max_len=32) or None)
            ref = svc.parse_any(body_str("ref"))
            p = pack.resolve(ref)
            return pack.id, p.reference

        if parts == ["bookmarks"]:
            if method == "GET":
                return {"bookmarks": [b.to_dict() for b in store.bookmarks()]}
            if method == "POST":
                tid, ref = resolve_body()
                bm, created = store.add_bookmark(tid, ref, body_str("label", required=False))
                return {"bookmark": bm.to_dict(), "created": created}
        if len(parts) == 2 and parts[0] == "bookmarks":
            if not parts[1].isdigit():
                raise HTTPError(404, "not_found", "Unknown bookmark.")
            bid = int(parts[1])
            if method == "DELETE":
                store.remove_bookmark(bid)
                return {"deleted": bid}
            if method == "PATCH":
                bm = store.update_bookmark_label(bid, body_str("label", required=False))
                return {"bookmark": bm.to_dict()}
        if parts == ["history"]:
            if method == "GET":
                return {"history": [h.to_dict() for h in store.history(_int(query, "limit", 30))]}
            if method == "POST":
                tid, ref = resolve_body()
                store.record(tid, ref)
                return {"recorded": ref.key()}
            if method == "DELETE":
                return {"cleared": store.clear_history()}
        raise HTTPError(404 if method == "GET" else 405, "not_found", "Unknown user endpoint or method.")

    # -- static files ---------------------------------------------------------------
    def static_path(self, path: str) -> Path | None:
        if path == "/" or path.startswith(SPA_PREFIXES) or path == "/index.html":
            return self.web_dir / "index.html"
        clean = posixpath.normpath(unquote(path))
        if "\x00" in clean or not clean.startswith("/") or "/." in clean:
            return None
        candidate = (self.web_dir / clean.lstrip("/")).resolve()
        try:
            candidate.relative_to(self.web_dir)
        except ValueError:
            return None
        return candidate if candidate.is_file() else None


def error_status(e: Exception) -> tuple[int, str]:
    if isinstance(e, HTTPError):
        return e.status, e.code
    if isinstance(e, (TranslationNotFoundError, NotFoundError)):
        return 404, e.code
    if isinstance(e, (ReferenceError_, SearchQueryError, UserDataError)) or type(e) is QBibleError:
        return 400, getattr(e, "code", "error")
    if isinstance(e, DataError):
        return 503, e.code
    return 500, "internal_error"


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        server_version = "qbible"
        sys_version = ""
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # no access log (privacy)
            pass

        # -- response helpers ------------------------------------------------------
        def _headers(self, status: int, ctype: str, length: int, extra: dict | None = None):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(length))
            for k, v in SECURITY_HEADERS.items():
                self.send_header(k, v)
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()

        def _json(self, status: int, data) -> None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self._headers(status, "application/json; charset=utf-8", len(body),
                          {"Cache-Control": "no-store"})
            if self.command != "HEAD":
                self.wfile.write(body)

        def _error(self, status: int, code: str, message: str) -> None:
            self._json(status, {"error": {"code": code, "message": message}})

        # -- checks -------------------------------------------------------------------
        def _host_ok(self) -> bool:
            if app.allowed_hosts is None:
                return True
            return (self.headers.get("Host") or "").lower() in app.allowed_hosts

        def _origin_ok(self) -> bool:
            origin = self.headers.get("Origin")
            if origin is None:
                return True
            host = self.headers.get("Host", "")
            return origin in (f"http://{host}", f"https://{host}")

        # -- dispatch ---------------------------------------------------------------
        def do_GET(self):
            self._handle("GET")

        def do_HEAD(self):
            self._handle("HEAD")

        def do_POST(self):
            self._handle("POST")

        def do_DELETE(self):
            self._handle("DELETE")

        def do_PATCH(self):
            self._handle("PATCH")

        def do_PUT(self):
            self._error(405, "method_not_allowed", "Method not allowed.")

        def do_OPTIONS(self):
            self._error(405, "method_not_allowed", "Cross-origin requests are not supported.")

        def _handle(self, method: str):
            try:
                if not self._host_ok():
                    self._error(421, "bad_host", "Unrecognised Host header.")
                    return
                url = urlsplit(self.path)
                path = url.path
                if len(self.path) > 4096:
                    self._error(414, "uri_too_long", "Request URI too long.")
                    return
                if path.startswith(API_PREFIX):
                    self._api(method, path, url.query)
                elif method in ("GET", "HEAD"):
                    self._static(path)
                else:
                    self._error(405, "method_not_allowed", "Method not allowed.")
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _api(self, method: str, path: str, qs: str):
            body = None
            if method in ("POST", "PATCH", "DELETE"):
                ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                if (not self.headers.get("X-QBible-Request") or not self._origin_ok()
                        or (method != "DELETE" and ctype != "application/json")):
                    self._error(403, "forbidden",
                                "State-changing requests must be same-origin JSON requests.")
                    return
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    length = -1
                if length < 0 or length > MAX_BODY:
                    self._error(413, "body_too_large", "Request body is too large.")
                    return
                raw = self.rfile.read(length) if length else b""
                try:
                    body = json.loads(raw.decode("utf-8")) if raw else {}
                except (UnicodeDecodeError, json.JSONDecodeError):
                    self._error(400, "invalid_json", "Request body is not valid JSON.")
                    return
                if not isinstance(body, dict):
                    self._error(400, "invalid_json", "Request body must be a JSON object.")
                    return
            elif method not in ("GET", "HEAD"):
                self._error(405, "method_not_allowed", "Method not allowed.")
                return
            query = {k: v[-1] for k, v in parse_qs(qs, keep_blank_values=True).items()}
            try:
                data = app.api("GET" if method == "HEAD" else method, path, query, body)
                self._json(200, data)
            except Exception as e:  # noqa: BLE001 — converted to a JSON error
                status, code = error_status(e)
                message = str(e) if status != 500 else "Internal error."
                if status == 500:
                    print(f"qbible: internal error handling {method} {path}: {e!r}", file=sys.stderr)
                self._error(status, code, message)

        def _static(self, path: str):
            file = app.static_path(path)
            if file is None:
                self._error(404, "not_found", "Not found.")
                return
            ext = file.suffix.lower()
            ctype = MIME.get(ext) or mimetypes.guess_type(file.name)[0] or "application/octet-stream"
            data = file.read_bytes()
            self._headers(200, ctype, len(data), {"Cache-Control": "no-cache"})
            if self.command != "HEAD":
                self.wfile.write(data)

    return Handler


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def create_server(service: BibleService, web_dir: Path, host: str = "127.0.0.1", port: int = 8737,
                  *, allow_remote: bool = False, user_data: bool = True) -> Server:
    if not is_loopback(host) and not allow_remote:
        raise QBibleError(
            f"Refusing to listen on non-loopback address '{host}'. qbible is local-only by default; "
            "add --allow-remote if you really intend to expose it (see docs/DEPLOYMENT.md)."
        )
    if not (web_dir / "index.html").is_file():
        raise DataError(f"Browser assets not found in {web_dir}.")
    service.pack()  # fail early if no translation is installed
    allowed = None
    if is_loopback(host):
        allowed = set()  # filled in once the port is known
    app = App(service, web_dir, user_data=user_data, allowed_hosts=allowed)
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    server_cls = type("QBibleServer", (Server,), {"address_family": family})
    try:
        httpd = server_cls((host.strip("[]"), port), make_handler(app))
    except OSError as e:
        raise DataError(f"Cannot listen on {host}:{port}: {e.strerror or e}") from None
    real_port = httpd.server_address[1]
    if allowed is not None:
        for h in ("127.0.0.1", "localhost", "[::1]"):
            allowed.add(f"{h}:{real_port}")
    httpd.app = app  # type: ignore[attr-defined]
    return httpd


def serve(service: BibleService, locs: Locations, *, host: str, port: int, open_browser: bool = False,
          allow_remote: bool = False, user_data: bool = True, out=None) -> int:
    out = out or sys.stderr
    httpd = create_server(service, locs.web, host, port, allow_remote=allow_remote, user_data=user_data)
    shown = "127.0.0.1" if host in ("127.0.0.1", "localhost") else host
    if ":" in shown and not shown.startswith("["):
        shown = f"[{shown}]"
    url = f"http://{shown}:{httpd.server_address[1]}/"
    print(f"qbible {__version__} is running at {url}", file=out)
    if not is_loopback(host):
        print("WARNING: listening on a non-loopback address. Anyone who can reach this machine "
              "can use it. Put it behind an HTTPS reverse proxy for public use.", file=out)
    print("Press Ctrl+C to stop.", file=out, flush=True)
    if open_browser:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()

    def _terminate(signum, frame):  # stop cleanly under systemd / kill
        raise KeyboardInterrupt

    try:
        signal.signal(signal.SIGTERM, _terminate)
    except ValueError:  # not in the main thread (e.g. embedded use)
        pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.", file=out)
    finally:
        httpd.server_close()
    return 0

# Security model and public deployment

## Local mode (default)

`qbible serve` is a **local, single-user** service:

| Control | Detail |
|---|---|
| Listening address | `127.0.0.1` only. Non-loopback addresses are refused without `--allow-remote`. |
| DNS-rebinding defence | On loopback, requests are accepted only with `Host: 127.0.0.1:PORT`, `localhost:PORT` or `[::1]:PORT` (others get 421). |
| Cross-site request forgery | No CORS headers. State-changing requests require a custom `X-QBible-Request` header (which forces a CORS pre-flight that is never approved), a JSON content type, and a same-origin `Origin` when present. |
| Content Security Policy | `default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'` and more. No inline scripts and no third-party origins. |
| Other headers | `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`, COOP/CORP `same-origin`, restrictive `Permissions-Policy`; `Cache-Control: no-store` on API responses. |
| Input handling | All SQL is parameterised. Search text is reduced to quoted alphanumeric tokens before it reaches FTS5. References are parsed and validated. Bodies are capped at 16 KiB and URIs at 4 KiB. Labels are length-limited. |
| Output encoding | JSON only from the API. The browser inserts all text with `textContent`, never `innerHTML`. Search highlights are structured segments. |
| Static files | Served only from the web directory. Paths are normalised and confined to it, and dotfiles and directory listings are refused. |
| Logging | No access log (searches and reading are private). Internal errors are printed to stderr without request bodies. |
| Privileges | Runs as the invoking user and never needs root. |
| Browser-presence watchdog | By default the server stops once all its pages are closed. Pages send `POST /api/v1/heartbeat` (subject to the same CSRF checks, so other sites cannot stop it). It is armed only by a page's first heartbeat and is off with `--keep-running`, with `server.exit_when_closed = false`, or on non-loopback addresses. |

The tests in `tests/test_server.py` and `tests/browser/` exercise these controls.

## Preparing a public website (future)

The architecture allows a public deployment of the browser interface. Recommended outline:

1. **Mode**: run with `--no-user-data`. Visitors' bookmarks and history then stay in their own
   browsers (`LocalStore`), so no personal data is stored on the server and **no accounts are
   needed**. Do not add accounts or password storage without a real requirement. If they are
   ever added, use a vetted framework, strong password hashing (Argon2id), CSRF tokens and
   rate limiting.
2. **Process**: run `qbible serve --host 127.0.0.1 --port 8737 --no-user-data --keep-running`
   as an unprivileged system user under systemd. **`--keep-running` is essential.** Without it,
   the browser-presence watchdog would stop the service as soon as visitors' pages close, and any
   visitor could end it on purpose. The watchdog is switched off automatically when listening on
   a non-loopback address, but a reverse proxy normally forwards to loopback, so pass the flag
   explicitly. For example:

   ```ini
   [Service]
   ExecStart=/usr/bin/qbible serve --host 127.0.0.1 --port 8737 --no-user-data --keep-running
   User=qbible
   Environment=QBIBLE_DATA_HOME=/var/lib/qbible QBIBLE_CONFIG_HOME=/etc/qbible
   NoNewPrivileges=yes
   ProtectSystem=strict
   ProtectHome=yes
   PrivateTmp=yes
   ReadWritePaths=/var/lib/qbible
   Restart=on-failure
   ```

3. **Reverse proxy and HTTPS**: put Nginx or Caddy in front, terminating TLS (Let's Encrypt).
   Keep qbible on loopback. Because the proxy forwards `Host: your.domain`, either have the proxy
   set `proxy_set_header Host 127.0.0.1:8737;` or bind qbible with `--allow-remote` on a
   private interface. The loopback Host allow-list stays in force when bound to 127.0.0.1.
4. **Headers at the proxy**: add `Strict-Transport-Security: max-age=31536000; includeSubDomains`.
   qbible already sends CSP and the other headers. Enable gzip or brotli for `application/json`,
   `text/css` and `text/javascript`.
5. **Rate limiting and abuse**: limit requests per IP at the proxy (e.g. Nginx `limit_req` around
   10 r/s with bursts) and cap request sizes (`client_max_body_size 16k`). The stdlib server
   is threaded and adequate for modest traffic. For heavy traffic, run several instances behind
   the proxy, or pre-render chapters as static files (every chapter is a pure function of the
   immutable pack).
6. **Access logging**: if logs are needed for operations, log at the proxy, exclude query
   strings (search terms), rotate them with logrotate, and keep them briefly (e.g. 14 days).
   Publish a privacy notice. Do not add analytics or tracking.
7. **Updates**: install security updates for the OS, Python and the proxy automatically
   (`unattended-upgrades`). Upgrade qbible by installing the new `.deb`. The translation pack
   is replaced atomically.
8. **Backups**: the Bible data can be rebuilt from source, so back up only configuration (and
   `/var/lib/qbible` if user data is ever enabled), together with the `.deb` and source tarball
   used.
9. **Secrets**: qbible needs none. Keep TLS keys readable only by the proxy, and never commit
   them.

Not yet implemented for public hosting: a separate production configuration file, built-in rate
limiting, and pre-rendered static output.

# Development guide

## Setup

```sh
git clone … qbible && cd qbible
make data                  # build/translations/kjv.sqlite (needs only python3)
./bin/qbible read John 1   # run from the source tree
make serve                 # browser interface from the source tree
npm install                # once, for browser tests (puppeteer-core only)
```

Requirements: Python 3.10+ (Ubuntu's `python3` has FTS5). The browser tests need Node.js 18+ and
Chrome/Chromium. Packaging needs `dpkg-deb`, `fakeroot` (optional) and `lintian` (optional).

Use temporary directories during development so that your own bookmarks are untouched:

```sh
export QBIBLE_DATA_HOME=/tmp/qb/data QBIBLE_CONFIG_HOME=/tmp/qb/config
```

`qbible serve` stops by itself when its browser pages close. Use `--keep-running` while working
with `curl` or other API clients. To make the watchdog fast for tests, set
`QBIBLE_WATCHDOG_TIMEOUTS=visible,hidden,grace` in seconds (defaults `15,150,5`; must satisfy
grace ≤ visible ≤ hidden). Puppeteer tip: in a background tab, use
`waitForFunction(..., { polling: 100 })` and `bringToFront()` before clicking, because
`requestAnimationFrame` does not run in hidden tabs.

## Code map and conventions

See [ARCHITECTURE.md](ARCHITECTURE.md). The rules are:

- Interfaces (`cli.py`, `interactive.py`, `server.py`, `web/`) go through `BibleService`. They
  never parse references, build SQL or format scripture themselves.
- Errors users can cause derive from `qbible.errors.QBibleError` and carry a readable message.
  The CLI maps them to exit codes and the server to HTTP statuses.
- All SQL uses bound parameters. FTS5 expressions are built only from sanitised tokens.
- Browser code must not use `innerHTML` or inline scripts and styles, because the CSP forbids
  them.
- Runtime code uses only the standard library. Development tools may add dependencies.
- Use British spelling in user-facing text.

## Tests

```sh
make test-python                          # python3 -m unittest discover -s tests -t . -v
python3 -m unittest tests.test_search     # one module
make test-browser                         # node --test tests/browser/browser.test.mjs
make test                                 # everything
```

| Suite | Covers |
|---|---|
| `test_data.py` | 66 books, counts vs. independent versification, sequential numbering, checkpoints, first/last verses, Unicode, integrity, metadata/attribution, source checksum, read-only access, tamper detection |
| `test_reference.py` | shared vectors in `spec/reference-cases.json` (full names, abbreviations, numbered books, ranges, Psalms, invalid books/chapters/verses, odd whitespace and punctuation), alias integrity, reference detection |
| `test_search.py` | words, phrases, case, apostrophes, punctuation, ligatures, empty queries, no matches, limits, pagination, ordering, filters, negation, prefix, SQL-injection attempts, context, performance |
| `test_cli.py` | help/version, reading, ranges, chapters, search, invalid references, pipe-friendly output, `NO_COLOR`, JSON, exit codes, navigation state, bookmarks, history, config, broken pipes |
| `test_interactive.py` | an interactive session driven through stdin |
| `test_userdata.py` | bookmarks (deduplication, labels), history, migrations, refusing newer schemas, file permissions |
| `test_importer.py` | TSV/VPL import, validation, malformed input, atomicity, adding a translation without breaking the KJV, CLI import/remove |
| `test_server.py` | every API endpoint, CSRF defences, Host checks, security headers, path traversal, body limits, loopback-only binding, user-data-disabled mode |
| `test_watchdog.py` | lease rules with a fake clock (visible, hidden, closing, reloads, several pages), plus real `qbible serve` processes: stops only after pages close, `--keep-running`, config setting, CSRF on heartbeats, refusal on non-loopback addresses |
| `tests/browser/` | navigation, URLs, Back/Forward, search and results, references, XSS, font size/family, themes, persistence, bookmarks, history, copying, keyboard, responsive layout, print, offline (no external requests), localStorage mode |

## Building and releasing

```sh
make deb          # dist/qbible_<version>_all.deb
make test-deb     # lintian + run the extracted package
make release      # data → all tests → deb → checks → dist/qbible-<version>.tar.gz → SHA256SUMS
```

To release a new version:

1. Bump `__version__` in `qbible/__init__.py` and the version in `packaging/qbible.1`.
2. Update `CHANGELOG.md`.
3. Run `make release`.

The package installs to `/usr/bin` and `/usr/share/qbible` (Debian FHS), runs as the invoking
user, and keeps per-user data in XDG directories.

Testing a real system installation needs root: `sudo apt install ./dist/qbible_*.deb`, then
`qbible --version`, then `sudo apt remove qbible`. `make test-deb` covers everything that can be
checked without root.

## App launcher and icon

`packaging/qbible.desktop.in` is the desktop entry template (`@BINDIR@` is replaced by
`scripts/stage.sh`). The icon source is `packaging/icons/qbible.svg`. After editing it,
regenerate the committed PNGs (16–512 px, rendered by the local Chrome) and the favicon:

```sh
node tools/render-icons.mjs
cp packaging/icons/qbible.svg web/assets/icon.svg
```

`make test-deb` validates the desktop entry (`desktop-file-validate`) and the icon sizes. The
Debian package relies on dpkg triggers to refresh the icon and desktop caches, and
`scripts/install.sh` refreshes them for per-user installs.

## Database changes

See [DATA.md](DATA.md#database-migrations).

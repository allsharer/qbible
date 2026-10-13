# qbible architecture

## Overview

```
                ┌─────────────────────┐       ┌───────────────────────────┐
  terminal ───▶ │ cli.py / interactive│       │ web/ (HTML, CSS, ES modules)│ ◀── browser
                └─────────┬───────────┘       └─────────────┬─────────────┘
                          │                                 │ JSON over HTTP (/api/v1)
                          │                   ┌─────────────▼─────────────┐
                          │                   │ server.py (loopback only) │
                          │                   └─────────────┬─────────────┘
                          ▼                                 ▼
                ┌───────────────────────────────────────────────────────┐
                │ services.py  BibleService (application services)       │
                └──────┬──────────────┬───────────────┬─────────────────┘
                       │              │               │
        ┌──────────────▼──┐  ┌────────▼───────┐  ┌────▼──────────────┐
        │ reference.py    │  │ search.py      │  │ userdata.py       │
        │ books.py        │  │ (FTS5 queries, │  │ (bookmarks,       │
        │ textfmt.py      │  │  highlighting) │  │  history,         │
        │ (pure rules)    │  └────────┬───────┘  │  migrations)      │
        └─────────────────┘           │          └────┬──────────────┘
                       ┌──────────────▼──────┐        │
                       │ repository.py       │        │
                       │ (translation packs, │        │
                       │  read-only SQLite)  │        │
                       └──────────┬──────────┘        │
                                  ▼                   ▼
                 /usr/share/qbible/translations/   ~/.local/share/qbible/user.sqlite
                 kjv.sqlite  (immutable)           (per user, read-write)
```

## Technology choices

| Decision | Choice | Reason |
|---|---|---|
| Core language | **Python 3.10+, standard library only** | Installed on every Ubuntu system; `sqlite3` with FTS5 built in; no dependency management for users; one language for the engine, CLI and server. |
| Bible storage | **SQLite translation packs** (one file per translation) | Portable, compact (8.4 MB with the search index), no server, readable by Android's built-in SQLite and by any other language. |
| Search | **SQLite FTS5** (contentless index over normalised text) | Fast enough for the full Bible on modest hardware (1–2 ms per query in the tests), with phrase queries, prefix queries and BM25 ranking. |
| User data | **Separate SQLite file per user**, numbered migrations | Keeps immutable scripture apart from personal data. The XDG location gives each OS user their own copy. |
| Browser UI | **Vanilla HTML/CSS/ES modules, no build step, no framework** | Nothing to download or bundle. Works offline, has a strict CSP and no supply-chain surface. The UI is small enough that a framework would add more than it saves. |
| Browser ↔ engine | **Local HTTP server (stdlib `http.server`) bound to 127.0.0.1**, versioned JSON API | Reuses the Python engine instead of duplicating parsing or search in JavaScript. The API contract is independent of the UI. |
| Packaging | **`dpkg-deb`-built `.deb`** plus a per-user installer | Native installation on Ubuntu with no build-dependency chain, and a no-root alternative. |

### Alternatives considered

- **Shared TypeScript core** (one engine for the browser, Node CLI and a future React Native or
  Capacitor app). This would allow a pure static site, but the CLI would need Node.js installed
  and SQLite access via WASM or native modules, adding heavy dependencies on Ubuntu.
- **Python core + API for Android**. This is rejected as the Android strategy because an Android
  app must not depend on a desktop process. The API exists for the *browser* and for future
  hosting only.
- **Portable, data-driven core (chosen for Android).** Everything an Android client needs to
  reproduce behaviour lives in language-neutral data rather than code: the translation-pack
  SQLite format, `books.json` (ids, names, aliases), the versification table, and
  `spec/reference-cases.json` (parser test vectors). A Kotlin implementation of the parser
  (about 300 lines) and equivalent full-text queries can then be
  verified against the same vectors. See [Android](#future-android-client), including the FTS5 caveat.

## Package layout

| Path | Purpose |
|---|---|
| `qbible/books.py`, `resources/books.json` | Canonical 66 books: stable USFM ids (`GEN`…`REV`), names, URL slugs, OSIS ids, testament, aliases. Book-name resolution (aliases, ordinals, Roman numerals, unambiguous prefixes, ambiguity errors). |
| `qbible/reference.py` | Reference parsing → `Reference`; validation against a versification → `Passage`; canonical display and stable keys (`JHN.3.16-JHN.3.21`); detection of references in free text. |
| `qbible/textfmt.py` | Conventions for stored text: `[supplied]` words, `¶` paragraph marks, folding for search. |
| `qbible/schema.py` | Translation pack schema v1. |
| `qbible/importer.py` | Builds packs from VPL or TSV sources, atomically. |
| `qbible/validation.py` | Pack validation report. |
| `qbible/build_data.py` | Reproducible build of the bundled KJV from `data/sources/`. |
| `qbible/repository.py` | Discovers packs; read-only verse retrieval; chapter navigation; random verse. |
| `qbible/search.py` | Query language → FTS5 expression; execution; highlight segments; context. |
| `qbible/userdata.py` | Bookmarks, history, schema migrations. |
| `qbible/services.py` | `BibleService`: the single entry point for all interfaces; JSON payloads. |
| `qbible/cli.py`, `interactive.py`, `termfmt.py`, `completion.py` | Command-line interface. |
| `qbible/server.py` | HTTP server, routing, security controls. |
| `qbible/paths.py`, `config.py` | File locations (XDG, overrides) and `config.ini`. |
| `web/` | Browser interface (`index.html`, `assets/css/app.css`, `assets/js/*.js`). |
| `data/sources/` | Vendored KJV source archive, its notice, and `SOURCES.json` (URL, checksum, metadata). |
| `spec/` | Language-neutral test vectors. |
| `tests/` | Python `unittest` suites and `tests/browser/` (Node + puppeteer-core). |
| `packaging/`, `scripts/` | Launcher, man page, Debian copyright, build/install/test scripts. |

## Data model

### Translation pack (`*.sqlite`, schema v1, read-only at runtime)

| Table | Columns | Notes |
|---|---|---|
| `meta` | `key`, `value` | `format`=`qbible-translation-pack`, `schema_version`, `id`, `name`, `abbreviation`, `language`, `licence`, `copyright`, `attribution`, `source_name`, `source_url`, `source_file`, `source_sha256`, `retrieved`, `versification`, `notes`, `verse_count`, `text_sha256`, `imported_at`, `importer` |
| `books` | `id` (USFM), `ord` (1–66), `name`, `testament` (`OT`/`NT`), `chapters` | only books present in the translation |
| `chapters` | `book_id`, `chapter`, `verses` | the versification **actually present** (not imposed) |
| `verses` | `id`, `book_id`, `chapter`, `verse`, `text` | `id = ord×1 000 000 + chapter×1000 + verse`, so `ORDER BY id` is canonical order and ranges are `BETWEEN` queries; `text` is exactly as in the source |
| `verses_fts` | FTS5 `body` (contentless, `rowid = verses.id`) | normalised text: no brackets/¶, lower-case, `’`→`'`, `æ`→`ae`, diacritics removed; tokenizer `unicode61 remove_diacritics 2` |

Translation identity is the pack's `meta.id`. Translations are discovered from
`QBIBLE_TRANSLATIONS_PATH`, then the user directory, then the shared directory. The first pack
found for an id wins, and the CLI refuses user imports that would shadow an installed id.

### User database (`user.sqlite`)

| Table | Columns |
|---|---|
| `schema_migrations` | `version`, `description`, `applied_at` |
| `bookmarks` | `id`, `translation`, `ref_key`, `label`, `created_at`, `updated_at`; `UNIQUE(translation, ref_key)` prevents duplicates |
| `history` | `id`, `translation`, `ref_key`, `opened_at` (re-opening moves an entry to the top; capped at 200) |

Only stable reference keys are stored, never copies of scripture. Keys are
translation-independent, so a bookmark can be opened in another translation.

## Reference parser

1. **Normalise** whitespace, non-breaking spaces, and Unicode dashes → `-`, and strip trailing
   punctuation.
2. **Split** into a book part and a number part (`(?P<book>[1-3]?...[^\d]+?)\s*(?P<nums>\d.*)?`).
3. **Resolve the book** via `book_key()`: lower-case; remove dots, spaces, hyphens and
   apostrophes; map leading `first|1st|i`, `second|2nd|ii`, `third|3rd|iii` to digits. Then look
   it up among ids, names, slugs, OSIS ids and listed aliases. Failing that, accept an
   **unambiguous prefix** of at least three letters of a full name. Ambiguous input lists the
   candidates. The alias table is checked at load time, so no key can map to two books.
4. **Numbers**: `3:16`, `3.16`, `3 16` and `3v16` are equivalent. Forms are `c`, `c-c`, `c:v`,
   `c:v-v` and `c:v-c:v`. Zero, numbers above 999 and verse lists are rejected. For
   single-chapter books (Obadiah, Philemon, 2–3 John, Jude), a bare number is a verse
   (`Jude 3`), except `1`, which is the whole book.
5. **Resolve** against the translation's own `chapters` table. Nonexistent chapters or verses
   raise `InvalidChapterError` or `InvalidVerseError` with a precise message. Reversed ranges
   are errors. **Nothing is clamped or redirected.**
6. **Format**: canonical display (`Psalm 23`, `Psalms 22-23`, `Genesis 1:1-2:3`) and stable keys.

**Reference detection in free text** (`find_references`) is deliberately conservative. A match
needs a chapter *and* verse with a known name or abbreviation (`Rom 8:28`), or a **full book
name** with a chapter (`Psalm 23`). Prefixes are not guessed, and every match is validated
against the translation. Single-chapter books without a colon are not linked.

## Search

1. **Parse** the query into terms: words, `"phrases"`, `-exclusions` and `prefix*`. Each term is
   reduced to `[a-z0-9]+` tokens with the same folding used for the index. A word that splits
   into several tokens (`brother's` → `brother s`) becomes an adjacent phrase.
2. **Build an FTS5 expression** only from double-quoted tokens, e.g.
   `"faith" + "without" + "works"` for a phrase or `"love" NOT "fear"`. This means no user text
   ever reaches FTS5 syntax or SQL, and the expression is passed as a bound parameter.
3. **Execute**: `count(*)` gives the total; results are paged with `LIMIT/OFFSET`, ordered by
   rowid (canonical) or `bm25()`. They can be restricted to a book or testament by rowid range.
4. **Highlight**: a regex built from the same tokens finds matches in the *display* text
   (tolerating curly apostrophes, punctuation between phrase words and `æ`). It returns
   **segments** `{text, supplied, match}`, so clients never insert HTML.
5. **Context**: neighbouring verse ids within the same chapter.

Phrase searches are never decomposed into separate words. `mode=phrase` treats the whole
input as one phrase. In the CLI, a single shell argument containing spaces is a phrase.

## Browser application

- **Routes**: `/bible/{translation}/{book-slug}[/{chapter}[/{verses}]]` and `/search?q=…`
  (documented in `docs/API.md`). The server returns `index.html` for these paths; `app.js` reads
  the path, calls the API and renders the result. History, refresh and bookmarks therefore work.
- **Rendering** uses DOM APIs and `textContent` only (no `innerHTML`). Supplied words are `<i>`.
  Verse numbers are buttons (keyboard-selectable) with `user-select: none`, so copied text is clean.
- **Storage adapters** (`store.js`): `ServerStore` (shared with the CLI) when the server enables
  user data, or `LocalStore` (browser `localStorage`) when it doesn't, e.g. a public deployment.
  A future sync backend would be a third adapter.
- **Display preferences** live in `localStorage` (`qbible.prefs.v1`). `boot.js` applies them
  before first paint to avoid a theme or size flash.

## Future Android client

This release is **not** an Android application. The intended path is:

1. **Data**: ship `kjv.sqlite` unchanged as an asset (schema v1). FTS5 is **not guaranteed** in
   Android's platform SQLite, so either bundle an SQLite build with FTS5 enabled (e.g.
   `requery/sqlite-android`) or rebuild the `verses_fts` index as FTS4 at packaging time. The
   query builder only uses phrase, prefix, AND/OR/NOT and rowid ranges, which FTS4 also
   supports (FTS4 has no `bm25()`, so relevance ordering would need `matchinfo`). This must be
   verified on target devices.
2. **Rules**: port `books.py`, `reference.py`, `textfmt.py` and the query builder in
   `search.py` to Kotlin, reading `books.json` directly. Verify against
   `spec/reference-cases.json` and a set of search vectors (to be exported from
   `tests/test_search.py`).
3. **User data**: implement the same `bookmarks` / `history` tables and reference keys (Room is
   fine). Keys are compatible with the desktop app, so import and export or a later sync can
   exchange them.
4. **No desktop dependency**: the app must not call `qbible serve`. The HTTP API is for
   browsers and future hosting.
5. **Remaining work**: UI, Android accessibility review, Play Store packaging and signing, device
   testing, and a shared search-vector file.

## Extending translations

New translations need no code changes: import a VPL/TSV file (or add an entry to
`data/sources/SOURCES.json` for bundled ones), and the repository discovers the new pack.
Versification differences are carried in each pack's `chapters` table. Book ids outside the
66-book canon are currently rejected by the catalogue. Supporting deuterocanonical books would
mean extending `books.json` with an extra canon flag; the schema already allows it.

# qbible

**qbible** is a modern, simple, fast and completely advertisement-free Bible application.
The first release contains the complete **King James Version** (all 66 books, 1,189 chapters,
31,102 verses) and offers two interfaces that share one engine:

- **Command line**: a complete terminal Bible reader for Ubuntu and other Linux systems.
- **Browser**: a calm, responsive reading interface served from your own computer.

There are no adverts, no tracking, no analytics, no accounts and no cloud services. After
installation, everything works offline.

---

## Contents

1. [Features](#features)
2. [Requirements](#requirements)
3. [Installation](#installation)
4. [Command line](#using-the-command-line)
5. [Browser interface](#using-the-browser-interface)
6. [Offline operation and privacy](#offline-operation-and-privacy)
7. [Files, settings and configuration](#files-settings-and-configuration)
8. [Additional translations](#additional-bible-translations)
9. [Running the tests](#running-the-tests)
10. [Building the Debian package](#building-the-debian-package)
11. [Uninstalling](#uninstalling)
12. [Reporting a problem](#reporting-a-problem)
13. [Licence and attribution](#licence-and-attribution)

---

## Features

| Feature | CLI | Browser |
|---|---|---|
| Read a verse, range, chapter or whole book | ✔ | ✔ |
| Flexible references (`jn 3:16`, `1 Cor 13:4-7`, `Song of Solomon 2`, `I John 4:8`, `Ps 23`) | ✔ | ✔ |
| Clear errors for nonexistent books, chapters and verses (never redirected elsewhere) | ✔ | ✔ |
| Previous / next chapter, across book boundaries | ✔ (`next`, `previous`) | ✔ |
| Word search, exact-phrase search, exclusions, prefixes | ✔ | ✔ |
| Total match counts and pagination | ✔ | ✔ (“Show more results”) |
| Search-term highlighting | ✔ (colour terminals) | ✔ |
| Open a passage typed into the search box | ✔ (`read`) | ✔ |
| Detect references inside search text and offer to open them | — | ✔ |
| Bookmarks with optional labels | ✔ | ✔ |
| Reading history | ✔ | ✔ |
| Translator-supplied words (*italic* in traditional KJVs) shown as italics, [brackets] or unmarked | ✔ | ✔ |
| Font size, font family, line spacing, light/dark/system theme | terminal's own | ✔ |
| Copy a verse or passage with its reference | (pipe the output) | ✔ |
| Interactive reading mode | ✔ (`shell`) | — |
| JSON output for scripting | ✔ (`--json`) | — |

Bookmarks and history are **shared** between the CLI and the browser on the same
computer, because both use the same per-user database.

---

## Requirements

- Ubuntu 22.04 or newer, or another Linux distribution with **Python 3.10+**. Ubuntu's
  `python3` includes the SQLite FTS5 full-text search that qbible needs.
- Any modern browser (Firefox, Chrome/Chromium, Edge, Safari) for the browser interface.
- No other runtime dependencies.

---

## Installation

### Option A: Debian package (system-wide, recommended on Ubuntu)

```sh
sudo apt install ./qbible_1.2.0_all.deb
```

This installs:

| Path | Contents |
|---|---|
| `/usr/bin/qbible` | the command |
| `/usr/share/qbible/` | program files, browser assets and the KJV database (read-only) |
| `/usr/share/man/man1/qbible.1.gz` | manual page (`man qbible`) |
| `/usr/share/bash-completion/completions/qbible` | tab completion |
| `/usr/share/applications/qbible.desktop` | **qbible** launcher in the app drawer (Activities / Show Apps) |
| `/usr/share/icons/hicolor/*/apps/qbible.{png,svg}` | app icon, 16–512 px plus scalable |
| `/usr/share/doc/qbible/` | README, licences, KJV validation report |

The package creates no system services and changes no system settings. Each user's
bookmarks and settings live in their own home directory.

### Option B: per-user installation (no root)

From a source checkout (with the KJV database built, see below):

```sh
make install-user           # or: scripts/install.sh [PREFIX]   (default ~/.local)
```

Make sure `~/.local/bin` is on your `PATH`. This also adds the app launcher and icon under
`~/.local/share/applications` and `~/.local/share/icons`. The launcher uses the full path to
`qbible`, so it works even if `~/.local/bin` is not on the desktop's `PATH`.

### Option C: run from the source tree

```sh
make data                   # builds build/translations/kjv.sqlite from the bundled source (≈3 s)
./bin/qbible read John 3:16
```

---

## Using the command line

```text
qbible [GLOBAL OPTIONS] COMMAND [ARGUMENTS]
```

### Quick reference

| Command | What it does | Example |
|---|---|---|
| `read REF` | Read a verse, range, chapter or book | `qbible read John 3:16-21` |
| `chapter BOOK N` | Read a whole chapter | `qbible chapter John 3` |
| `next` / `previous` (`prev`) | Next/previous chapter from your last reading position | `qbible next` |
| `next --from REF` | Next chapter after a given passage | `qbible next --from Ruth 4` |
| `random` | A random verse (`--testament OT\|NT`) | `qbible random` |
| `books` | List books, chapter counts and abbreviations | `qbible books --testament NT` |
| `search WORDS` | Search words or a quoted phrase | `qbible search "fear not" --context` |
| `ref REF` | Check and normalise a reference | `qbible ref 1jn4.8` |
| `bookmark add REF [--label T]` | Add a bookmark | `qbible bookmark add Ps 23 --label Comfort` |
| `bookmark list` (`bookmarks`) | List bookmarks with their ids | `qbible bookmarks` |
| `bookmark open ID` | Read a bookmarked passage | `qbible bookmark open 2` |
| `bookmark label ID TEXT` | Change a bookmark's label | `qbible bookmark label 2 Psalm of comfort` |
| `bookmark remove ID` | Delete a bookmark | `qbible bookmark remove 2` |
| `history [clear]` | Show or clear reading history | `qbible history --limit 50` |
| `shell` | Interactive reading mode | `qbible shell` |
| `serve [--open] [--keep-running]` | Start the browser interface (stops when its pages are closed) | `qbible serve --open` |
| `translations` | List installed translations and licences | `qbible translations` |
| `import FILE ...` | Import another legally obtained translation | see [below](#additional-bible-translations) |
| `remove-translation ID` | Remove a translation you imported | `qbible remove-translation web` |
| `validate` | Check the integrity and completeness of a translation | `qbible validate` |
| `config list\|get\|set\|unset` | Show or change settings | `qbible config set reading.supplied brackets` |
| `paths` | Show where files are read and stored | `qbible paths` |
| `completion bash` | Print the bash completion script | `qbible completion bash` |

**Global options** (before or after the command): `-t/--translation ID`,
`--colour auto|always|never`, `--plain` (also `--no-colour`), `-h/--help`, `-V/--version`.

**Reading options** (`read`, `chapter`, `next`, `previous`, `random`, `search`):

| Option | Meaning |
|---|---|
| `-N`, `--no-numbers` / `-n`, `--numbers` | hide/show verse numbers |
| `--supplied plain\|brackets\|italic` | how to show words the translators supplied (default: italic in colour terminals, otherwise plain) |
| `--pilcrows` | show the KJV's ¶ paragraph marks |
| `--no-heading` | omit the reference heading |
| `--no-wrap` | do not wrap long lines (wrapping only happens on a terminal) |
| `--no-history` | do not record this passage as your reading position |
| `--json` | machine-readable output |

### Reading scripture

```sh
qbible read John 3:16
qbible read John 3:16-21
qbible read Psalm 23
qbible read Genesis 1:1-10
qbible read Romans 8
qbible read 1 John 4:8
qbible read Rev 21:1-4
qbible read Gen 1:1-2:3          # across chapters
qbible read Jude 3               # single-chapter books: the number is a verse
```

References accept full names, common abbreviations (`Gen`, `Ps`, `Mt`, `Jn`, `1 Cor`,
`Phil`, `Philem`, `Rev` …), unambiguous beginnings of names (`Deuter`), numbered books written
as `1 John`, `1John`, `1jn`, `I John` or `First John`, separators `3:16`, `3.16`, `3 16` or
`3v16`, and hyphens or en/em dashes in ranges. `qbible books` lists every book with its
abbreviations. Lists of separate verses (`John 3:16,18`) are not supported; read them one at a time.

Invalid references are reported precisely and never replaced with another passage:

```text
$ qbible read John 22
qbible: John has 21 chapters; there is no chapter 22.
$ qbible read Jo 3:16
qbible: 'Jo' is ambiguous. Did you mean: Joshua, Job, Joel, John, Jonah?
```

### Navigating

`qbible next` and `qbible previous` continue from your **saved reading position**, which is
the most recent passage you opened with `read`, `chapter`, `next`, `previous`, a bookmark, the
interactive shell or the browser. The command tells you which position it used. If there is no
saved position, it says so and exits with status 1. Add `--no-history` to `read` to look
something up without moving your position.

`qbible shell` opens an **interactive reading session**:

```text
John 3> n                  next chapter        p      previous chapter
John 4> 7                  chapter 7 of the current book
John 7> Rom 8:28           any reference
Romans 8:28> s "fear not"  search ('more' for the next page)
Romans 8:28> b Promise     bookmark the current passage with a label
Romans 8:28> bookmarks     list;  'open ID' opens one
Romans 8:28> q             quit (or Ctrl+D)
```

### Searching

```sh
qbible search faith                        # one word
qbible search "faith without works"        # exact phrase (one quoted argument)
qbible search "Jesus wept"
qbible search faith hope charity           # all of these words, any order
qbible search love --limit 50              # more results per page
qbible search love --limit 50 --page 2     # the next page
qbible search "fear not" --context         # with the verses before and after
qbible search grace --book Romans          # one book only (or --testament NT)
qbible search love --count                 # just the number of matching verses
qbible search love --sort relevance        # best matches first (default: Bible order)
```

Search syntax (inside one argument you can combine forms, e.g. `'"fear not" -afraid'`):

| You type | Matches |
|---|---|
| `faith hope` | verses containing both words |
| `"faith without works"` | the exact phrase: adjacent words, in order |
| `love -fear` | “love” but not “fear” |
| `believ*` | words starting with “believ” (believe, believed, believeth …) |
| `--phrase` / `--words` / `--any` | treat all the words as one phrase / require all / match any |

Searching ignores case and punctuation, so `"fear not abram"` finds “Fear not, Abram”.
`brother's` (with a straight or curly apostrophe) finds *brother’s*. `caesar` finds *Cæsar*.
Words the translators supplied are searchable.

The summary line (`63 verses match "fear not"; showing 1-20 …`) and hints go to **standard
error**, so standard output contains only the results.

### Pipes, colour and accessibility

Colour and line wrapping are used only when output goes to a terminal. When you pipe or redirect
output, you get plain text with no escape codes or decorations:

```sh
qbible read Psalm 119 | less
qbible read John 3:16 --no-heading --no-numbers | wl-copy
qbible search love --json | jq '.total'
```

`--plain`, `--colour never` and the `NO_COLOR` environment variable disable colour. The
output does not rely on colour to convey meaning, so it reads well with screen readers.

### Exit status

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | nothing found (no search results; no saved reading position) |
| 2 | usage error (unknown command or option, invalid search) |
| 3 | invalid scripture reference, or unknown bookmark id |
| 4 | data or configuration problem (translation missing, file unreadable) |
| 130 | interrupted (Ctrl+C) |

### Shell completion

The Debian package installs bash completion automatically. For other installs, add this to
`~/.bashrc`:

```sh
eval "$(qbible completion bash)"
```

---

## Using the browser interface

**From the app drawer:** open Activities (or Show Apps), search for **qbible** and click it.
qbible starts in the background and opens in your default browser. When you close the qbible
tab or window, the background server stops by itself. Clicking the icon again while qbible is
running just opens another qbible page. If the browser never connects (for example it failed
to open), the background server gives up after a minute. You can pin qbible to the dock with
right-click → *Pin to Dash*.

**From a terminal:**

```sh
qbible serve --open          # starts http://127.0.0.1:8737/ and opens your browser
qbible serve --port 9000     # another port (0 = any free port)
qbible serve --keep-running  # don't stop when the browser pages are closed
```

**The server stops by itself when you close qbible in your browser.** Once every qbible tab or
window has been closed, it shuts down within a few seconds. You can also stop it at any time
with **Ctrl+C**. Details:

- It only starts watching once a page has connected, so `qbible serve` without `--open` waits
  for you to open the address.
- Reloading a page, navigating within qbible, or having several qbible tabs open does not stop
  it. Neither does switching to other tabs: browsers slow down background tabs, so a hidden
  qbible tab is allowed up to about 2½ minutes between check-ins. If you close your last
  visible qbible tab while another one sits in the background, the server stops when that one
  is closed too.
- If the server stops while a page is still open (for example after Ctrl+C), the page shows a
  notice. It reconnects by itself when you run `qbible serve` again on the same port.
- To keep the server running regardless, use `--keep-running` or
  `qbible config set server.exit_when_closed false`.

The server listens only on this computer (127.0.0.1). It refuses other addresses unless you pass
`--allow-remote` (see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)).

### Reading and navigating

- Choose a **Book**, **Chapter** and optionally a **Verse** and **to** verse at the top, or use
  the **← / →** buttons (or the arrow keys) for the previous and next chapter.
- Type a reference such as `John 3:16` or `1 cor 13:4-7` in the box at the top and press
  **Go**. A recognised reference opens directly, with a link to search for the words instead.
  Anything else is searched. A recognisable reference that does not exist (for example
  `John 22`) is reported, not redirected.
- Every passage has its own address, so refresh, Back/Forward and browser bookmarks all work.
  See [URL structure](docs/API.md#browser-urls), e.g. `http://127.0.0.1:8737/bible/kjv/john/3/16-21`.
- **Select verses** by clicking or tapping a verse number (Shift+click selects a range). The bar
  at the bottom copies the text **with its reference**, bookmarks it, or copies a link.
  **Copy passage** copies everything shown.
- Normal text selection and copying work as usual. Verse numbers are left out of copied text.

### Choosing a translation

With only the KJV installed, a **KJV** badge is shown. Once you have
[imported another translation](#additional-bible-translations), the badge becomes a
**translation picker**:

- Choosing a translation keeps you on the **same passage**
  (`/bible/kjv/john/3` → `/bible/web/john/3`). If that passage doesn't exist in the other
  translation (a book it doesn't include, or a verse its versification lacks), qbible says so and
  offers links to the translations that have it. It never substitutes a different passage.
- On the search page, the search re-runs in the chosen translation (`/search?q=…&t=web`).
- The translation is part of every address, so links, Back/Forward and browser bookmarks always
  open the translation they were made in. qbible bookmarks and history remember their
  translation too, and entries from another translation are labelled, e.g. `John 3:16 (WEB)`.
- Your last choice is remembered in this browser and used when you open qbible without an
  address and with no reading history.

### Searching

The search page offers **All words** (quotes for phrases), **Exact phrase** or **Any word**, a
testament filter, and Bible-order or relevance ordering. Matches are highlighted, each result
links to its passage, and **Show more results** loads the next 25. If your search text contains
a reference (e.g. `all things work together Romans 8:28`), qbible offers a link to open it.
Searches run only when you submit, not on every keystroke.

### Fonts and themes

Open **Aa Display**:

- **Text size**: **A−** / **A+** (14–32 px in 2 px steps) and **Reset** (20 px).
- **Font**: Serif or Sans-serif (your system's fonts; nothing is downloaded).
- **Theme**: System (follows your operating system), Light or Dark.
- **Line spacing**, **Layout** (paragraphs or one verse per line), **supplied words**
  (italic, [brackets] or unmarked) and **verse numbers** on/off.

Settings are saved in your browser and survive restarts. **Esc** closes the panel.

### Bookmarks and history

Use **Bookmark** on a passage (or select verses and use the bar's **Bookmark**), optionally add
a label, and **Save bookmark**. Click **Bookmarked** again to remove it. Bookmarks and **Recent
reading** appear in the side panel, which is always visible on wide screens and opened with
**☰** on narrow ones. Each entry opens its passage. **✕** removes a bookmark, and **Clear
history** empties the history.

### Keyboard

**←/→** previous and next chapter · **/** jump to the search box · **Tab** reaches every
control (verse numbers included; **Enter** selects) · **Esc** closes panels and clears a
selection. Focus moves to the passage heading after navigation, for screen readers.

### Printing

Printing a passage uses a print stylesheet that hides navigation and controls.

---

## Offline operation and privacy

- The KJV text, search index, browser code, styles and icon are all installed locally. Nothing
  is loaded from the internet: no CDNs, web fonts or external APIs. The browser tests check that
  every request goes to the local server.
- The browser interface talks only to the qbible process on your own computer.
- qbible keeps **no logs**. Search terms and reading history are never sent anywhere. History is
  stored only in your own user database.
- There is **no service worker / PWA** in this release. The browser interface works offline
  because its server runs on your computer: start `qbible serve` and use the page as normal
  without a network connection.

---

## Files, settings and configuration

| What | Default location | Override |
|---|---|---|
| Bundled translations (read-only) | `/usr/share/qbible/translations/` | `QBIBLE_SHARE_DIR` |
| Browser assets | `/usr/share/qbible/web/` | `QBIBLE_WEB_DIR` |
| Bookmarks and history | `~/.local/share/qbible/user.sqlite` | `QBIBLE_DATA_HOME` (or `XDG_DATA_HOME`) |
| Imported translations | `~/.local/share/qbible/translations/` | `QBIBLE_DATA_HOME`; extra dirs via `QBIBLE_TRANSLATIONS_PATH` |
| Settings | `~/.config/qbible/config.ini` | `QBIBLE_CONFIG_HOME` (or `XDG_CONFIG_HOME`) |
| Browser display settings | the browser's local storage | — |
| Logs | none | — |

`qbible paths` shows the locations in effect. Every user has separate bookmarks and settings,
and nothing personal is stored in the installation directory. The user database is created with
permissions `0600`.

### Settings (`qbible config`)

| Setting | Default | Meaning |
|---|---|---|
| `reading.translation` | `kjv` | default translation |
| `reading.verse_numbers` | `true` | show verse numbers |
| `reading.supplied` | `auto` | `auto`, `plain`, `brackets` or `italic` |
| `reading.pilcrows` | `false` | show ¶ marks |
| `display.colour` | `auto` | `auto`, `always`, `never` |
| `search.limit` | `20` | results per page |
| `server.host` | `127.0.0.1` | listening address for `serve` |
| `server.port` | `8737` | port for `serve` |
| `server.exit_when_closed` | `true` | stop `serve` once all its browser pages are closed |

```sh
qbible config set reading.supplied brackets
qbible config unset reading.supplied
```

---

## Additional Bible translations

The first release bundles **only the KJV**. The data layer is translation-neutral: each
translation is a separate, self-contained SQLite *translation pack*. You can import another
translation **that you are legally entitled to use**:

```sh
# Tab-separated: book<TAB>chapter<TAB>verse<TAB>text   (book = USFM id like JHN, or a name)
qbible import mybible.tsv --id web --name "World English Bible" --licence "Public Domain" \
       --source-url https://example.org/web --retrieved 2026-10-13

# eBible.org "verse per line" downloads (*_vpl.zip) are also accepted:
qbible import eng-web_vpl.zip --format vpl --id web --name "World English Bible" --licence "Public Domain"

qbible translations
qbible -t web read John 3:16
qbible -t web search "living water"
qbible validate -t web
qbible remove-translation web
```

Imports are validated (structure, numbering, versification compared with the KJV, which is a
warning for other translations because versifications legitimately differ) and stored in your
user directory. They cannot replace the bundled KJV. Once more than one translation is
installed, the browser shows a **translation picker** next to the qbible name (see
[below](#choosing-a-translation)). `qbible config set reading.translation web` changes the
default for both the CLI and the browser.

---

## Running the tests

```sh
make test-python      # 100+ Python tests: data, parser, search, CLI, user data, importer, HTTP/security
make test-browser     # end-to-end browser tests (headless Chrome via puppeteer-core)
make test             # both
```

The browser tests need Node.js 18+ and an installed Chrome or Chromium (`CHROME_PATH` to override).
`npm install` fetches only `puppeteer-core`, which is a development-only dependency and doesn't
download a browser. Tests use temporary data directories and never touch your bookmarks.

---

## Building the Debian package

```sh
make deb              # -> dist/qbible_1.2.0_all.deb  (dpkg-deb, no root needed)
make test-deb         # lintian + run the extracted package (read, search, validate, server)
make release          # data, all tests, .deb, package checks, source tarball and SHA256SUMS
```

---

## Uninstalling

- Debian package: `sudo apt remove qbible`. Your own data in `~/.local/share/qbible` and
  `~/.config/qbible` is never removed by the package. Delete those folders yourself if you wish.
- Per-user install: `make uninstall-user` (or `scripts/uninstall.sh [PREFIX] [--purge]`;
  `--purge` also deletes your bookmarks, history, imports and settings).

---

## Reporting a problem

Please include `qbible --version`, your distribution, the exact command or browser address,
and what you expected. `qbible validate` and `qbible paths` output are also useful. Report
problems to the project maintainers through the project's issue tracker (or, until one is
published, to the maintainer address in the package: `dpkg -s qbible | grep Maintainer`).
**If you believe a verse's text is wrong**, give the reference and the wording you expected.
Text accuracy is the highest priority.

---

## Licence and attribution

- qbible software: MIT licence (`LICENSE`).
- The King James Version text: public domain outside the United Kingdom; the text is courtesy of
  the CrossWire Bible Society and eBible.org. In the UK, rights in the KJV are vested in the Crown.
  See `THIRD_PARTY_NOTICES.md` for the full source, licence, checksum and UK notice.

Further documentation: [Architecture](docs/ARCHITECTURE.md) · [Development](docs/DEVELOPMENT.md) ·
[Bible data](docs/DATA.md) · [HTTP API and URLs](docs/API.md) · [Public deployment](docs/DEPLOYMENT.md) ·
[Changelog](CHANGELOG.md)

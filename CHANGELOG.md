# Changelog

## 1.2.0 — 2026-10-13

- `qbible serve` now stops by itself once all of its browser pages are closed. Pages send
  heartbeats; background tabs, reloads and in-app navigation do not stop it, and it only starts
  watching after a page connects. Disable with `--keep-running` or
  `server.exit_when_closed = false`. It is always off on non-loopback addresses.
- Open pages show a notice if the server stops, and reconnect when it is started again.
- App launcher: the `.deb` and per-user install add a **qbible** entry with an icon to the
  Ubuntu app drawer (`qbible.desktop`, hicolor icons 16–512 px and SVG). Launching opens the
  browser interface and the server stops when its pages close. Launching again while it is
  running reuses the running server, and a launcher-started server stops after a minute if no
  page connects.
- New app icon (also used as the browser favicon).
- Fixed a harmless "BrokenPipeError" message from `qbible --version | head -0` and similar.

## 1.1.0 — 2026-10-13

- Browser: translation picker, shown when more than one translation is installed. Switching
  keeps the current passage or search. Passages or books missing from the chosen translation
  are reported with links to translations that have them. The choice is remembered per browser.
  Bookmarks and history from other translations are labelled with their abbreviation.
- Search URLs carry the translation (`/search?q=…&t=ID`) when it isn't the default.

## 1.0.0 — 2026-10-13

First release.

- Complete King James Version (66 books, 1,189 chapters, 31,102 verses) from eBible.org /
  CrossWire, validated against an independent versification table.
- `qbible` CLI: read, chapter, next/previous (stored reading position), random, books,
  search (words, phrases, exclusions, prefixes, pagination, context, JSON), ref, bookmarks,
  history, interactive shell, translations, import/remove-translation, validate, config,
  paths, bash completion.
- Browser interface (`qbible serve`): book/chapter/verse selectors, direct reference entry,
  stable URLs, search with highlighting and reference detection, font size/family, line
  spacing, layout, light/dark/system themes, bookmarks with labels, reading history,
  copy with reference, keyboard support, responsive layout, print stylesheet.
- Loopback-only local server with CSP, CSRF and DNS-rebinding defences.
- Debian package and per-user installer.

Not included: Android app, service worker/PWA, a translation picker in the browser,
curated cross-references.

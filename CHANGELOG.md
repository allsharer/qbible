# Changelog

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

# HTTP API (v1) and browser URLs

The API is served by `qbible serve` under `/api/v1/`. It is versioned independently of the
browser interface: incompatible changes will use `/api/v2/`. All responses are JSON
(`application/json; charset=utf-8`). Errors have the form

```json
{"error": {"code": "invalid_chapter", "message": "John has 21 chapters; there is no chapter 22."}}
```

with status 400 (bad input), 403 (refused state-changing request), 404 (unknown endpoint,
translation or bookmark), 413 (body too large), 421 (unrecognised Host) or 503 (no data).

`t` (or `translation`) selects a translation. It defaults to the configured one (`kjv`).

## Browser URLs

| URL | Shows |
|---|---|
| `/` | your last reading position (or Genesis 1) |
| `/bible/{t}/{book}` | chapter 1 of a book |
| `/bible/{t}/{book}/{c}` | a chapter, e.g. `/bible/kjv/psalms/23` |
| `/bible/{t}/{book}/{c1}-{c2}` | a chapter range |
| `/bible/{t}/{book}/{c}/{v}` | a verse, e.g. `/bible/kjv/john/3/16` |
| `/bible/{t}/{book}/{c}/{v1}-{v2}` | a range, e.g. `/bible/kjv/john/3/16-21` |
| `/bible/{t}/{book}/{c1}/{v1}-{c2}:{v2}` | a range across chapters |
| `/search?q=…&mode=auto\|phrase\|any&testament=OT\|NT&sort=canonical\|relevance&t=ID` | search (`t` is omitted for the default translation) |

`{book}` is the lower-case slug from `books.json` (`genesis`, `1-samuel`, `song-of-solomon`,
`john`, `1-john`, …). These URLs are stable.

## Reading

| Method & path | Parameters | Returns |
|---|---|---|
| `GET /api/v1/info` | — | `app`, `version`, `api_version`, `user_data` (bool), `default_translation`, `watchdog` (`{"interval_ms": N}` when the server stops after its pages close, otherwise `null`) |
| `GET /api/v1/translations` | — | `translations[]` (id, name, abbreviation, language, licence, copyright, attribution, source_url, versification, verse_count), `default` |
| `GET /api/v1/translations/{t}/books` | — | `books[]`: id, order, name, slug, osis, testament, `chapters`, `verses[]` (count per chapter) |
| `GET /api/v1/passage` | `ref` (text such as `John 3:16` or key such as `JHN.3.16`), `t` | passage (below). A whole-book reference returns chapter 1. |
| `GET /api/v1/random` | `t`, `testament` | a passage with one verse |
| `GET /api/v1/resolve` | `q`, `t` | `{"match": {key, display, book, start, end}}` or `{"match": null, "error": {code, message}}` (status 200 either way) |
| `GET /api/v1/references` | `text` (≤ 2000 chars), `t` | `references[]`: `{start, end, text, key, display}` found in the text |

Passage payload:

```json
{
  "translation": {"id": "kjv", "name": "King James Version", "abbreviation": "KJV"},
  "reference": {"key": "JHN.3.16", "display": "John 3:16", "book": {...},
                "start": {"chapter": 3, "verse": 16}, "end": {"chapter": 3, "verse": 16},
                "whole_chapters": false, "chapter_verse_count": 36},
  "chapters": [{"chapter": 3, "verses": [
      {"verse": 16, "text": "For God so loved…", "raw": "¶ For God so loved…", "paragraph": true,
       "parts": [{"text": "For God so loved…", "supplied": false}]}]}],
  "previous": {"key": "JHN.2", "display": "John 2", "book": {...}, "chapter": 2},
  "next": {"key": "JHN.4", "display": "John 4", "book": {...}, "chapter": 4}
}
```

## Search

`GET /api/v1/search` with `q` (required), `mode` (`auto`, `phrase`, `all`, `any`), `limit`
(1–500, default 25), `offset`, `sort` (`canonical`, `relevance`), `book`, `testament`,
`context` (0–5) and `t`.

```json
{"query": "\"fear not\"", "mode": "auto", "sort": "canonical", "terms": ["\"fear not\""],
 "total": 63, "offset": 0, "limit": 25, "has_more": true,
 "results": [{"reference": {"key": "GEN.15.1", "display": "Genesis 15:1", "book": {...}, "chapter": 15, "verse": 1},
              "text": "After these things…",
              "segments": [{"text": "After these things … saying, ", "supplied": false, "match": false},
                           {"text": "Fear not", "supplied": false, "match": true}, ...],
              "context_before": [], "context_after": []}]}
```

Clients should render `segments` as text (marking `match` and `supplied`) and never as HTML.

## Heartbeat (browser-presence watchdog)

`POST /api/v1/heartbeat` with `{"client": "<page id>", "visible": true, "closing": false}`. The
same CSRF requirements apply as for user data (below). `client` is a random id per page load
(1–64 characters from `A-Z a-z 0-9 _ -`). Pages send it every `info.watchdog.interval_ms` while
visible, on visibility changes, and with `"closing": true` (a `keepalive` request) when the
page is closed or reloaded. Returns `{"watchdog": bool}`. Heartbeats are accepted but ignored when
the watchdog is off. See `qbible/watchdog.py` for the lease rules.

## User data (local mode only)

Available when the server runs with user data enabled (the default for `qbible serve`). With
`--no-user-data` these endpoints return 404 and the browser keeps its own data.

State-changing requests **must** send `X-QBible-Request: 1`. POST and PATCH must also send
`Content-Type: application/json`. Any `Origin` header must match the host. The body is limited
to 16 KiB.

| Method & path | Body / parameters | Returns |
|---|---|---|
| `GET /api/v1/user/bookmarks` | — | `bookmarks[]`: id, translation, key, reference, label, created_at, updated_at |
| `POST /api/v1/user/bookmarks` | `{"ref": "...", "translation": "kjv", "label": "..."}` | `{"bookmark": {...}, "created": bool}`. An existing bookmark is returned rather than duplicated. |
| `PATCH /api/v1/user/bookmarks/{id}` | `{"label": "..."}` | `{"bookmark": {...}}` |
| `DELETE /api/v1/user/bookmarks/{id}` | — | `{"deleted": id}` |
| `GET /api/v1/user/history` | `limit` | `history[]`: id, translation, key, reference, opened_at |
| `POST /api/v1/user/history` | `{"ref": "...", "translation": "kjv"}` | `{"recorded": key}` |
| `DELETE /api/v1/user/history` | — | `{"cleared": n}` |

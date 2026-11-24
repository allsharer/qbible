# qbible → Android: handover

**For:** a Claude agent working in a sandbox.
**From:** the agent that built qbible 1.3.0 on the user's Ubuntu machine (fhdt), 2026-11-23.
**Goal:** turn **qbible**, a desktop Bible reader (CLI and browser), into a **native Android app**.

> **How to work:**
> 1. **Copy this folder to `~/workspace/`** before you start: `cp -a /shared/bibleApp ~/workspace/`.
> 2. **Do all the work in `~/workspace/bibleApp/`.** Don't work in `/shared/`.
> 3. **When you finish, copy the finished directory back to `/shared/bibleApp/`**, with your
>    **`HANDBACK.md`** at its top level (see [What to hand back](#what-to-hand-back)).
>
> `/shared/` is the same folder as the user's `~/ai-shared/` on their machine. The agent there
> will read `HANDBACK.md` first. Nothing you leave outside `/shared/` will reach the user.
>
> In the rest of this file, paths such as `qbible/` and `prebuilt/` are relative to your
> working copy, `~/workspace/bibleApp/`.

---

## What's in this folder

| Path | What it is |
|---|---|
| `HANDOVER.md` | This file. |
| `qbible/` | A full git clone of the project (all history) at **`3261fe4` "Release 1.3.0"**, the released version. The `origin` remote points at GitHub, but **don't push** (see the rules). |
| `prebuilt/kjv.sqlite` | The built King James Version database (schema v1, 8.4 MB, with FTS5 search index). It is the same file that ships in the 1.3.0 `.deb`. Checksum in `kjv.sqlite.sha256`. |
| `prebuilt/kjv-validation.txt` | The validation report for that database (66 books, 1,189 chapters, 31,102 verses). |
| `prebuilt/SHA256SUMS-desktop-1.3.0` | Checksums of the desktop 1.3.0 release files, for reference only. |

If you need to rebuild the database, run `python3 -m qbible.build_data` inside `qbible/` (Python
3.10+, standard library only, no network). The source text is `qbible/data/sources/eng-kjv_vpl.zip`.

## Read these first, in this order

1. `qbible/docs/ARCHITECTURE.md`, especially **"Future Android client"** and **"Alternatives
   considered"**. That section is the agreed plan. Follow it unless you find a real reason not
   to, and if you change course, say why in `HANDBACK.md`.
2. `qbible/prompt.txt`: the user's original master prompt for qbible. Its requirements
   (no adverts, no tracking, offline, accurate references, clear errors) apply to the Android
   app too.
3. `qbible/README.md`: the feature table shows what the desktop app does.
4. `qbible/docs/DATA.md`: the database format and the text conventions (`[supplied words]`, `¶`).
5. `qbible/qbible/books.py`, `reference.py`, `textfmt.py` and `search.py`: these are the rules you
   will port.

## The plan (from ARCHITECTURE.md, in short)

1. **Data.** Ship `kjv.sqlite` unchanged as an app asset (copy it to app storage on first run;
   it is read-only). Android's built-in SQLite does **not** promise FTS5, so either:
   - bundle an SQLite with FTS5 (for example `requery/sqlite-android`), **or**
   - rebuild `verses_fts` as FTS4 when packaging the app (FTS4 has no `bm25()`; rank with `matchinfo`).

   Pick one, explain the choice, and test that search works.
2. **Rules.** Port the book-name lookup, reference parsing and validation, and the search query
   builder to **Kotlin**. Read `qbible/qbible/resources/books.json` directly; don't copy the book
   list into code.
3. **Proof that the port matches.** Run every case in `qbible/spec/reference-cases.json` as a
   unit test (same `display`, same `key`, same error `code`). Also export search test vectors
   from `qbible/tests/test_search.py` into a new shared file (for example
   `qbible/spec/search-cases.json`), and test the Kotlin search against it.
4. **User data.** Bookmarks and reading history, with the **same reference keys** as the desktop
   app (for example `JHN.3.16-JHN.3.21`), so they can be exported or synced later. Room is fine.
5. **No desktop dependency.** The app must work entirely on the phone. It must not call
   `qbible serve` or any network service.

## What the app should do (match the desktop app)

- Read a verse, range, chapter or whole book. Previous and next chapter, crossing book boundaries.
- A reference box that accepts everything the desktop accepts (details below).
- Clear errors for a book, chapter or verse that doesn't exist. **Never** jump to some other passage instead.
- Word search, exact-phrase search, exclusions and prefixes, with match counts, paging and highlighting.
- If someone types a reference into the search box, offer to open it.
- Bookmarks with optional labels, and reading history (remember where the reader was).
- Translator-supplied words shown as *italics*, [brackets] or plain (a setting).
- Font size, font family, line spacing, and light/dark/system theme.
- Copy or share a verse or passage together with its reference.
- Fully offline. No adverts, analytics, accounts, tracking, or network permission (unless you
  have a strong reason, which you must explain).
- Good accessibility: TalkBack labels, scalable text, enough contrast.

## Reference input rules (the user set these on 2026-11-23)

These already work on the desktop in 1.3.0 and are covered by `spec/reference-cases.json`. The
Android app must behave the same way.

| Input | Means |
|---|---|
| `mar 4:15` | Mark 4:15 |
| `mar 4:1-15` or `mar 4:1-4:15` | Mark 4:1 to 4:15 |
| `mar 4:1-5:2` | Mark 4:1 to Mark 5:2 |
| `mar 4:1-` | Mark 4:1 to the last verse of chapter 4 (shown as "Mark 4:1-41") |
| `mar 4v15`, `4v1-5v2` | `v` works anywhere `:` does, in upper or lower case, and the two can be mixed |
| `1sa 4:1`, `1sam 4:1`, `1s 4:1` | 1 Samuel 4:1. Numbered books are written with no space; show them with the space ("1 Samuel") |
| `gen`, `gene`, `genes`, `genesi`, `genesis` | Genesis. Any start of a book name with 3 or more letters that matches only one book works. Case doesn't matter |
| `jn`, `ps`, `ge`, `mk` … | Short aliases from `books.json` also work. The user wants to keep them |

The user's standard abbreviations are all in `books.json`, and a test lists them
(`test_standard_three_letter_abbreviations` in `qbible/tests/test_reference.py`). Among them:
Sng/Sol, Eze/Ezk, Joe/Jol, Nah/Nam, Mar/Mrk, Joh/Jhn, Php/Phi, Phm/Phl, Jam/Jas, 1Jo/1Jn.

## Rules for working

- **Work inside `qbible/`** on a new local git branch called **`android`**. Put the Android
  project in **`qbible/android/`** (Gradle, Kotlin). Commit as you go, with clear messages.
- **Don't push to GitHub, and don't change the git remote.** The user reviews and merges on their own machine.
- **Don't change desktop behaviour.** If you change shared files (`books.json`, `spec/`,
  `docs/`), the Python tests must still pass. Run them inside `qbible/`:
  ```sh
  mkdir -p build/translations && cp ../prebuilt/kjv.sqlite build/translations/   # or: python3 -m qbible.build_data
  python3 -m unittest discover -s tests -t .      # expect: Ran 127 tests ... OK
  ```
  Without that database, most tests are **skipped** quietly rather than failing. Make sure the
  count is 127 and nothing is skipped. (`build/` is git-ignored.) If you can't run them, say so.
- **App id:** use a placeholder such as `org.qbible.app`, and say in `HANDBACK.md` that the user
  must confirm it before publishing.
- **Signing:** a debug build only. **Don't create release keys or put any secrets** in the
  folder. Write the release-signing steps down for the user instead.
- **Licences:** the KJV text is public domain outside the UK (see `qbible/THIRD_PARTY_NOTICES.md`
  and `packaging/copyright`). Add any new libraries and their licences to `THIRD_PARTY_NOTICES.md`.
- **Be honest about what you could not do.** If the sandbox has no Android SDK, no emulator or
  no network, write the code anyway, test what you can (for example plain JVM unit tests for the
  Kotlin rules), and list clearly what was **not** built or **not** tested.

## What to hand back

When you finish, copy your working copy back to **`/shared/bibleApp/`**, replacing what is
there. The result must have the same layout as this folder:

| Path | Contents |
|---|---|
| `/shared/bibleApp/HANDBACK.md` | **Required.** Your report (see below). |
| `/shared/bibleApp/qbible/` | The whole git repository, including `.git`, with your work committed on the `android` branch. |
| `/shared/bibleApp/apk/` | A debug APK if you managed to build one, plus its SHA-256. |
| `/shared/bibleApp/prebuilt/` | Any database you changed (for example an FTS4 version), with a note on how it was made. |

**Don't copy back** build outputs that rebuild themselves (`.gradle/`, `build/`, `node_modules/`,
`local.properties`, caches), because `/shared/` is the user's own disk. Keep `HANDOVER.md` and
`prebuilt/kjv.sqlite`. For example:

```sh
rsync -a --delete \
  --exclude '.gradle/' --exclude 'build/' --exclude 'node_modules/' \
  --exclude 'local.properties' --exclude '__pycache__/' --exclude '.idea/' \
  ~/workspace/bibleApp/ /shared/bibleApp/
```

Make the copy back the **last step**, after `HANDBACK.md` is written. Then list `/shared/bibleApp/`
to check that it is all there.

**`HANDBACK.md` must cover:**

1. **Summary:** what works, in a few lines.
2. **What you did:** the main decisions (FTS5 or FTS4, libraries, minimum Android version,
   architecture, UI toolkit) and why.
3. **Changes outside `android/`:** every file you touched, so the user can check that the desktop
   app is unaffected.
4. **Commits:** `git log --oneline main..android`.
5. **Tests:** what ran, with pass and fail counts: Kotlin unit tests, the reference vectors,
   search vectors, any instrumented or emulator tests, and the Python tests.
6. **Not done or not tested:** be specific (for example "never ran on a real device", "no
   emulator, so the UI is untested").
7. **How to build and install:** exact commands on Ubuntu (SDK packages, `./gradlew assembleDebug`,
   `adb install …`), and the steps for release signing.
8. **Questions for the user:** anything only they can decide (app name and id, icon, Play Store or
   sideloading, minimum Android version).

# Bible data: source, licence, import and validation

## The KJV source

| | |
|---|---|
| Text | King James Version (Authorized Version), standardised 1769 text |
| Publisher of electronic text | eBible.org, “King James Version + Apocrypha” (`eng-kjv`), edition 2026-09-26; text courtesy of the CrossWire Bible Society and eBible.org |
| File | `data/sources/eng-kjv_vpl.zip` (vendored, unchanged) |
| URL | https://ebible.org/Scriptures/eng-kjv_vpl.zip |
| Details | https://ebible.org/Scriptures/details.php?id=eng-kjv |
| Retrieved | 2026-10-13 |
| SHA-256 | `970b0564b6816737928ebfb2fec910b96586e242c6311927f3b6c507b76418f3` (checked on every build) |
| Licence | Public domain (per eBible.org's notice in `data/sources/eng-kjv_about.htm`), **except in the United Kingdom**, where the Crown's letters patent restrict printing and importing printed copies |

### Why this source

- eBible.org states the licence explicitly, and the archive includes its own notice.
- It is the CrossWire KJV text, widely used and checked by Bible software projects.
- It is plain UTF-8 with stable book codes. It preserves the KJV's supplied-word markers
  (`[ ]`), paragraph marks (`¶`), typographic apostrophes (’), ligatures (æ) and the em dash in
  Exodus 32:32.
- No commercial website was scraped, and the text is not altered.

### Licence checks performed

1. The text: public domain except for the UK Crown rights described above, as stated by the
   source. This is recorded in the pack's `meta.licence` / `meta.copyright` and shown by
   `qbible translations`.
2. The archive and metadata: eBible.org places no extra restrictions on redistributing the
   public-domain text. Its notice is shipped in `/usr/share/doc/qbible/`.
3. Validation data: verse counts per chapter come from the CrossWire SWORD `canon.h` table.
   Only the numeric facts are used; no GPL code is distributed. See `THIRD_PARTY_NOTICES.md`.

### What is imported

- The 66 books of the Protestant canon, Genesis to Revelation: **31,102 verses in 1,189
  chapters**.
- The archive's 14 Apocrypha books (5,720 verses) are **excluded** and listed in the build report.
- Text is stored exactly as in the source. Psalm titles are part of verse 1 (the source's
  convention), and Psalm 119's Hebrew-letter headings are not present in the source.

## Building the database

```sh
make data            # = python3 -m qbible.build_data
```

This verifies the source checksum, imports with `qbible.importer` into a temporary file,
validates it, writes `build/translations/kjv.sqlite` atomically and writes
`build/translations/kjv-validation.txt`. If validation fails, the pack is deleted and the build
exits with status 4. The build is deterministic apart from the `imported_at` timestamp.

## Validation report

`qbible validate` (or the build) checks:

| Check | KJV result |
|---|---|
| SQLite `integrity_check` | pass |
| pack format/schema; translation metadata and licence; source provenance | pass |
| all 66 canonical books present, canonical order | pass |
| no empty verses | pass |
| sequential chapter and verse numbering (no gaps) | pass |
| chapter tables agree with the verse rows | pass |
| chapter and verse counts match the independent KJV versification table (1,189 chapters, 31,102 verses) | pass |
| full-text index covers every verse | pass |
| verse-text SHA-256 matches the value recorded at import (detects later modification) | pass |
| 21 checkpoint verses match exactly (incl. Genesis 1:1, John 3:16, John 11:35, Esther 8:9, Acts 8:37, 1 John 5:7, Revelation 22:21) | pass |
| first verse Genesis 1:1, last verse Revelation 22:21 | pass |
| special characters preserved (’ æ — ¶) | pass |

The most recent report is installed as `/usr/share/doc/qbible/kjv-validation.txt.gz`.

The checkpoint verses (`qbible/resources/checkpoints/kjv.json`) were compared with the
well-known 1769 KJV wording when they were recorded. From then on, they detect corruption,
truncation, encoding damage or mis-numbering in later builds.

## Importing other translations

Only import texts you are entitled to use. `qbible import` requires `--licence`.

**TSV format**: UTF-8, one verse per line, `book<TAB>chapter<TAB>verse<TAB>text`. The book can be
a USFM id (`JHN`) or any name qbible recognises. Lines starting with `#` are ignored.

**VPL format**: eBible.org's `*_vpl.txt`, or the `*_vpl.zip` that contains it.

```sh
qbible import FILE --id ID --name NAME --licence TEXT [--format tsv|vpl] [--abbreviation ABBR]
       [--language en] [--copyright TEXT] [--attribution TEXT] [--source-name TEXT]
       [--source-url URL] [--retrieved YYYY-MM-DD] [--versification kjv] [--force]
```

Imports go to `~/.local/share/qbible/translations/ID.sqlite` and are validated straight away. A
failed validation removes the import. Missing books or versification differences are
**warnings** for imported translations (partial and differently versified texts are legitimate).
Pass `--versification kjv` to make them failures. Duplicate verses, malformed lines, unknown books
and empty verses are always errors, and no partial file is left behind.

### Adding a bundled translation (developers)

1. Put the source file in `data/sources/` and add an entry to `SOURCES.json` (file, format,
   sha256, url, retrieved, translation metadata).
2. Optionally add `qbible/resources/checkpoints/<id>.json`.
3. Run `python3 -m qbible.build_data --translation <id>`, and update `scripts/stage.sh` to ship
   the new pack.

## Database migrations

- **Translation packs** are immutable, versioned with `meta.schema_version` (currently 1), and
  rebuilt from source rather than migrated. A pack with an unsupported schema version is
  skipped and reported (`qbible translations` shows a warning). When the schema changes,
  increase `PACK_SCHEMA_VERSION`, update `schema.py`, `importer.py` and `repository.py`, and
  rebuild.
- **User databases** are migrated in place by numbered migrations in
  `qbible/userdata.py: MIGRATIONS`. Each runs in an `IMMEDIATE` transaction (safe if the CLI and
  server start at the same time) and is recorded in `schema_migrations`. A database from a newer
  qbible is refused, not modified. To add a migration, append
  `(N, "description", "SQL; SQL")` to `MIGRATIONS` and add a test in `tests/test_userdata.py`
  that migrates a database created at version N−1.

### Backing up user data

Copy `~/.local/share/qbible/user.sqlite` while qbible is not writing to it, or use
`sqlite3 ~/.local/share/qbible/user.sqlite ".backup /path/to/backup.sqlite"`.

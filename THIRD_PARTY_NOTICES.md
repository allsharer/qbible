# Third-party notices

qbible's own code is under the MIT licence (see `LICENSE`). It has **no third-party
runtime dependencies**: it uses only the Python standard library and the system's
SQLite, and the browser interface uses only code in this repository.

## King James Version text

| | |
|---|---|
| Work | The Holy Bible, King James Version (Authorized Version), standardised 1769 text |
| Electronic source | eBible.org, file `eng-kjv_vpl.zip` (“King James Version + Apocrypha”), edition dated 2026-09-26 |
| URL | https://ebible.org/Scriptures/eng-kjv_vpl.zip (details: https://ebible.org/Scriptures/details.php?id=eng-kjv) |
| Retrieved | 2026-10-13 |
| SHA-256 | `970b0564b6816737928ebfb2fec910b96586e242c6311927f3b6c507b76418f3` |
| Credit | “This free text of the King James Version of the Holy Bible is brought to you courtesy of the Crosswire Bible Society and eBible.org.” |
| Licence | Public domain (as stated by eBible.org), with the United Kingdom exception below |

The source's own notice (`data/sources/eng-kjv_about.htm`) says:

> Letters patent issued by King James with no expiration date means that to print this
> translation in the United Kingdom or import printed copies into the UK, you need
> permission. Currently, the Cambridge University Press, the Oxford University Press, and
> Collins have the exclusive right to print this Bible translation in the UK. This royal
> decree has no effect outside of the UK, where this work is firmly in the Public Domain.

qbible redistributes the electronic text unchanged (only the 14 Apocrypha books contained in
the same archive are omitted). Users and redistributors in the United Kingdom should consider
the Crown's rights described above, particularly for printing.

## KJV versification table (validation only)

The expected chapter and verse counts in `qbible/resources/versification/kjv.json` were
extracted (by `tools/extract_sword_versification.py`) from the numeric `vm[]` table in
`include/canon.h` of the CrossWire SWORD Project
(https://crosswire.org/svn/sword/trunk/include/canon.h, GPL-2.0). Only the numbers
(factual data) are used; no SWORD source code is included or distributed.

## Development-only tools (not distributed)

The browser tests use `puppeteer-core` (Apache-2.0) from npm with a locally installed
Chrome. These are not part of the application or the Debian package.

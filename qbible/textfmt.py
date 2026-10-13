"""Verse text conventions shared by every interface.

The stored KJV text is kept exactly as published by the source:

* ``[word]`` marks words supplied by the translators (printed in italics in
  traditional KJV editions);
* a leading ``¶`` (pilcrow) marks the start of a paragraph;
* typographic apostrophes (’) and ligatures (æ) are preserved.

This module turns that raw text into structured parts for display, and into
a normalised form used only for the full-text index.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

PILCROW = "¶"
_SUPPLIED_RE = re.compile(r"\[([^\[\]]*)\]")


@dataclass(frozen=True)
class Part:
    text: str
    supplied: bool = False

    def to_dict(self) -> dict:
        return {"text": self.text, "supplied": self.supplied}


def starts_paragraph(raw: str) -> bool:
    return raw.lstrip().startswith(PILCROW)


def strip_pilcrow(raw: str) -> str:
    return raw.replace(PILCROW, "").strip()


def parts(raw: str) -> list[Part]:
    """Split raw verse text into plain and translator-supplied parts."""
    text = strip_pilcrow(raw)
    out: list[Part] = []
    pos = 0
    for m in _SUPPLIED_RE.finditer(text):
        if m.start() > pos:
            out.append(Part(text[pos : m.start()]))
        if m.group(1):
            out.append(Part(m.group(1), True))
        pos = m.end()
    if pos < len(text):
        out.append(Part(text[pos:]))
    return out


def plain(raw: str) -> str:
    """Reading text without brackets or pilcrows (words are kept)."""
    return "".join(p.text for p in parts(raw))


def render(raw: str, supplied: str = "plain", pilcrows: bool = False,
           italic_on: str = "", italic_off: str = "") -> str:
    """Render raw verse text for a terminal or plain-text output.

    ``supplied`` is ``"plain"`` (no marking), ``"brackets"`` (as in the
    source) or ``"italic"`` (wrapped in the given escape sequences).
    """
    out = []
    for p in parts(raw):
        if p.supplied and supplied == "brackets":
            out.append(f"[{p.text}]")
        elif p.supplied and supplied == "italic":
            out.append(f"{italic_on}{p.text}{italic_off}")
        else:
            out.append(p.text)
    text = "".join(out)
    if pilcrows and starts_paragraph(raw):
        text = f"{PILCROW} {text}"
    return text


_FOLD = str.maketrans({"’": "'", "‘": "'", "ʼ": "'", "`": "'",
                       "æ": "ae", "Æ": "Ae", "œ": "oe", "Œ": "Oe"})


def fold(text: str) -> str:
    """Fold ligatures, curly apostrophes and diacritics; keep everything else."""
    t = text.translate(_FOLD)
    t = unicodedata.normalize("NFKD", t)
    return "".join(ch for ch in t if not unicodedata.combining(ch))


def search_text(raw: str) -> str:
    """Normalised text stored in the full-text index (never displayed)."""
    return fold(plain(raw)).lower()


def tokens(text: str) -> list[str]:
    """Split text into search tokens exactly as the FTS5 index does.

    The index uses SQLite's ``unicode61`` tokenizer over :func:`search_text`
    output, which separates on anything that is not a letter or digit. After
    folding, verse text is ASCII, so this regular expression is equivalent.
    """
    return re.findall(r"[a-z0-9]+", fold(text).lower())

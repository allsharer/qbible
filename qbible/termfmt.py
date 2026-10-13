"""Terminal output: optional colour, wrapping and passage/search layout.

Colour is used only when enabled *and* the output is a terminal, unless the
user forces it. ``NO_COLOR`` (https://no-color.org) and ``TERM=dumb`` are
respected. When output is piped, no escape sequences and no wrapping are
emitted, so the text is clean for other programs.
"""

from __future__ import annotations

import os
import shutil
import sys
import textwrap
from dataclasses import dataclass

from .textfmt import render


def colour_enabled(choice: str, stream=None) -> bool:
    stream = stream or sys.stdout
    if choice == "always":
        return True
    if choice == "never":
        return False
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    return hasattr(stream, "isatty") and stream.isatty()


@dataclass
class Style:
    enabled: bool

    def _wrap(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled and text else text

    def heading(self, t: str) -> str:
        return self._wrap("1", t)

    def ref(self, t: str) -> str:
        return self._wrap("1;36", t)

    def num(self, t: str) -> str:
        return self._wrap("2", t)

    def match(self, t: str) -> str:
        return self._wrap("1;33", t)

    def dim(self, t: str) -> str:
        return self._wrap("2", t)

    @property
    def italic_on(self) -> str:
        return "\033[3m" if self.enabled else ""

    @property
    def italic_off(self) -> str:
        return "\033[23m" if self.enabled else ""


@dataclass
class ReadOptions:
    numbers: bool = True
    supplied: str = "plain"  # plain | brackets | italic
    pilcrows: bool = False
    heading: bool = True
    wrap: int = 0  # 0 = no wrapping


def terminal_width(stream=None) -> int:
    stream = stream or sys.stdout
    if not (hasattr(stream, "isatty") and stream.isatty()):
        return 0
    return max(40, min(shutil.get_terminal_size((100, 24)).columns, 100))


def wrap_verse(prefix: str, text: str, width: int, indent: int) -> str:
    if not width:
        return prefix + text
    # Wrap on plain text, then the escape codes stay attached to words.
    lines = textwrap.wrap(text, width=max(20, width - indent), break_long_words=False,
                          break_on_hyphens=False)
    if not lines:
        return prefix
    pad = " " * indent
    return prefix + lines[0] + "".join("\n" + pad + ln for ln in lines[1:])


def format_passage(view_dict: dict, style: Style, opts: ReadOptions) -> str:
    """Format a passage (``PassageView.to_dict()``) for the terminal."""
    out: list[str] = []
    ref = view_dict["reference"]
    tr = view_dict["translation"]["abbreviation"]
    chapters = view_dict["chapters"]
    multi = len(chapters) > 1
    if opts.heading:
        out.append(style.heading(f"{ref['display']} ({tr})"))
    width_num = max(len(str(v["verse"])) for ch in chapters for v in ch["verses"])
    book = ref["book"]["name"] if ref["book"]["id"] != "PSA" else "Psalm"
    for i, ch in enumerate(chapters):
        if multi:
            if out:
                out.append("")
            out.append(style.heading(f"{book} {ch['chapter']}"))
        elif out and i == 0:
            out.append("")
        for v in ch["verses"]:
            text = render(v["raw"], opts.supplied, opts.pilcrows, style.italic_on, style.italic_off)
            if opts.numbers:
                n = str(v["verse"]).rjust(width_num)
                prefix = style.num(n) + " "
                indent = width_num + 1
            else:
                prefix, indent = "", 0
            out.append(wrap_verse(prefix, text, opts.wrap, indent))
    return "\n".join(out)


def format_segments(segments: list[dict], style: Style, supplied: str) -> str:
    out = []
    for s in segments:
        t = s["text"]
        if s["supplied"] and supplied == "brackets":
            t = f"[{t}]"
        elif s["supplied"] and supplied == "italic":
            t = f"{style.italic_on}{t}{style.italic_off}"
        out.append(style.match(t) if s["match"] else t)
    return "".join(out)

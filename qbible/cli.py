"""The ``qbible`` command-line interface.

Exit codes:
    0  success
    1  nothing found (no search results, no reading position yet)
    2  usage error (bad options or arguments)
    3  invalid scripture reference, or unknown bookmark id
    4  data or configuration problem (translation missing, unreadable files)
  130  interrupted (Ctrl+C)
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from pathlib import Path

from . import __version__
from .books import catalogue
from .config import SETTINGS, Config
from .errors import (
    DataError,
    NotFoundError,
    QBibleError,
    ReferenceError_,
    SearchQueryError,
    TranslationNotFoundError,
    UserDataError,
)
from .paths import locations
from .search import MODES, SORTS
from .services import BibleService
from .termfmt import ReadOptions, Style, colour_enabled, format_passage, format_segments, terminal_width

EXIT_OK, EXIT_NOTHING, EXIT_USAGE, EXIT_REFERENCE, EXIT_DATA, EXIT_INTERRUPTED = 0, 1, 2, 3, 4, 130

EPILOG = """\
examples:
  qbible read John 3:16            one verse
  qbible read Psalm 23             a whole chapter
  qbible read 1 Cor 13:4-7         a range
  qbible search "faith without works"
  qbible search love --limit 50 --page 2
  qbible next                      continue from your last reading position
  qbible shell                     interactive reading mode
  qbible serve --open              browser interface on http://127.0.0.1:8737

Run 'qbible COMMAND --help' for details of a command."""


class CLIError(Exception):
    def __init__(self, message: str, code: int = EXIT_USAGE):
        super().__init__(message)
        self.code = code


# --------------------------------------------------------------------------- context


class Context:
    def __init__(self, args: argparse.Namespace, out=None, err=None):
        self.args = args
        self.out = out or sys.stdout
        self.err = err or sys.stderr
        self.locs = locations()
        self.config = Config(self.locs.config_file)
        colour = getattr(args, "colour", None) or self.config.get("display.colour")
        if getattr(args, "plain", False):
            colour = "never"
        self.style = Style(colour_enabled(colour, self.out))
        self._service: BibleService | None = None

    @property
    def service(self) -> BibleService:
        if self._service is None:
            self._service = BibleService.from_environment(self.locs)
            if getattr(self.args, "translation", None):
                self._service.default_translation = self.args.translation.lower()
        return self._service

    @property
    def translation(self) -> str:
        return self.service.default_translation

    def print(self, *parts: str) -> None:
        print(*parts, file=self.out)

    def note(self, message: str) -> None:
        """Informational message: stderr, so stdout stays clean for pipes."""
        print(message, file=self.err)

    def json(self, data) -> None:
        json.dump(data, self.out, ensure_ascii=False, indent=2)
        self.out.write("\n")

    def read_options(self) -> ReadOptions:
        a = self.args
        supplied = getattr(a, "supplied", None) or self.config.get("reading.supplied")
        if supplied == "auto":
            supplied = "italic" if self.style.enabled else "plain"
        numbers = self.config.get_bool("reading.verse_numbers")
        if getattr(a, "no_numbers", False):
            numbers = False
        elif getattr(a, "numbers", False):
            numbers = True
        return ReadOptions(
            numbers=numbers,
            supplied=supplied,
            pilcrows=getattr(a, "pilcrows", False) or self.config.get_bool("reading.pilcrows"),
            heading=not getattr(a, "no_heading", False),
            wrap=0 if getattr(a, "no_wrap", False) else terminal_width(self.out),
        )


# --------------------------------------------------------------------------- commands


def _join(words: list[str]) -> str:
    return " ".join(words).strip()


def show_passage(ctx: Context, view, *, record: bool) -> int:
    if getattr(ctx.args, "json", False):
        ctx.json(view.to_dict())
    else:
        ctx.print(format_passage(view.to_dict(), ctx.style, ctx.read_options()))
    if record and not getattr(ctx.args, "no_history", False):
        try:
            ctx.service.user.record(view.translation.id, view.reference)
        except UserDataError as e:
            ctx.note(f"qbible: warning: reading position not saved: {e}")
    return EXIT_OK


def cmd_read(ctx: Context) -> int:
    view = ctx.service.passage(_join(ctx.args.reference), ctx.args.translation)
    return show_passage(ctx, view, record=True)


def cmd_chapter(ctx: Context) -> int:
    words = list(ctx.args.reference)
    if not words:
        raise CLIError("Give a book and chapter, e.g. 'qbible chapter John 3'.")
    ref = ctx.service.parse(_join(words))
    if ref.has_verses:
        raise CLIError("'chapter' takes a book and chapter only; use 'qbible read' for verses.")
    if ref.is_whole_book:
        raise CLIError(f"Which chapter of {ref.book.name}? e.g. 'qbible chapter {ref.book.name} 1'.")
    view = ctx.service.passage(ref, ctx.args.translation)
    return show_passage(ctx, view, record=True)


def cmd_step(ctx: Context, step: int) -> int:
    svc = ctx.service
    if ctx.args.start:
        start = svc.parse(_join(ctx.args.start))
        translation = ctx.args.translation or svc.default_translation
    else:
        pos = svc.user.last_position()
        if pos is None:
            ctx.note("No reading position is saved yet. Read a passage first, "
                     "e.g. 'qbible read John 1', or use --from REFERENCE.")
            return EXIT_NOTHING
        start = pos.reference
        translation = ctx.args.translation or pos.translation
        ctx.note(f"Last position: {start.display()}")
    target = svc.step_from(start, step, translation)
    if target is None:
        ctx.note("You are at the " + ("beginning" if step < 0 else "end") + " of the Bible.")
        return EXIT_NOTHING
    view = svc.passage(target, translation)
    return show_passage(ctx, view, record=True)


def cmd_random(ctx: Context) -> int:
    view = ctx.service.random_verse(ctx.args.translation, ctx.args.testament)
    return show_passage(ctx, view, record=False)


def cmd_books(ctx: Context) -> int:
    books = ctx.service.books(ctx.args.translation)
    if ctx.args.testament:
        books = [b for b in books if b["testament"] == ctx.args.testament]
    if ctx.args.json:
        ctx.json([{k: v for k, v in b.items() if k != "verses"} for b in books])
        return EXIT_OK
    cat = catalogue()
    last = None
    for b in books:
        if not ctx.args.testament and b["testament"] != last:
            if last is not None:
                ctx.print("")
            ctx.print(ctx.style.heading("Old Testament" if b["testament"] == "OT" else "New Testament"))
            last = b["testament"]
        aliases = ", ".join(sorted(cat.get(b["id"]).aliases, key=len)[:3])
        ctx.print(f"  {b['name']:<17} {b['chapters']:>3} ch   {ctx.style.dim(b['id'] + '  ' + aliases)}")
    return EXIT_OK


def cmd_search(ctx: Context) -> int:
    a = ctx.args
    terms = list(a.query)
    if a.phrase:
        mode, query = "phrase", _join(terms)
    elif a.words:
        mode, query = "all", _join(terms)
    elif a.any:
        mode, query = "any", _join(terms)
    else:
        # A shell argument containing spaces was quoted by the user: treat it
        # as an exact phrase, e.g. qbible search "fear not".
        mode = "auto"
        query = " ".join(
            f'"{t}"' if (" " in t.strip() and '"' not in t) else t for t in terms
        ).strip()
    limit = a.limit if a.limit is not None else ctx.config.get_int("search.limit")
    if a.page < 1:
        raise CLIError("--page must be 1 or more.")
    offset = (a.page - 1) * limit
    result = ctx.service.search(
        query, a.translation, mode=mode, limit=limit, offset=offset, sort=a.sort,
        book=a.book, testament=a.testament, context=a.context,
    )
    if a.count:
        ctx.print(str(result.total))
        return EXIT_OK if result.total else EXIT_NOTHING
    data = ctx.service.search_dict(result, a.translation)
    if a.json:
        ctx.json(data)
        return EXIT_OK if result.total else EXIT_NOTHING

    terms_text = " ".join(data["terms"])
    if not result.total:
        ctx.note(f"No verses match {terms_text}.")
        return EXIT_NOTHING
    if not result.hits:
        ctx.note(f"Page {a.page} is past the end: {result.total} verses match {terms_text}.")
        return EXIT_NOTHING
    opts = ctx.read_options()
    width = max(len(r["reference"]["display"]) for r in data["results"])
    for i, r in enumerate(data["results"]):
        disp = r["reference"]["display"]
        if a.context:
            if i:
                ctx.print("")
            for c in r["context_before"]:
                ctx.print(ctx.style.dim(f"  {c['reference']['display']}  {c['text']}"))
            ctx.print(f"{ctx.style.ref(disp)}  {format_segments(r['segments'], ctx.style, opts.supplied)}")
            for c in r["context_after"]:
                ctx.print(ctx.style.dim(f"  {c['reference']['display']}  {c['text']}"))
        else:
            pad = " " * (width - len(disp))
            ctx.print(f"{ctx.style.ref(disp)}{pad}  {format_segments(r['segments'], ctx.style, opts.supplied)}")
    first, last = result.offset + 1, result.offset + len(result.hits)
    noun = "verse matches" if result.total == 1 else "verses match"
    msg = f"{result.total} {noun} {terms_text}; showing {first}-{last}."
    if result.has_more:
        msg += f" For more, add --page {a.page + 1} (or --limit N)."
    ctx.note(msg)
    return EXIT_OK


def cmd_ref(ctx: Context) -> int:
    text = _join(ctx.args.reference)
    svc = ctx.service
    p = svc.resolve(text, ctx.args.translation)
    data = {
        "input": text,
        "display": p.display(),
        "key": p.key(),
        "book": p.book.to_dict(),
        "start": {"chapter": p.start[0], "verse": p.start[1]},
        "end": {"chapter": p.end[0], "verse": p.end[1]},
    }
    if ctx.args.json:
        ctx.json(data)
    else:
        ctx.print(f"{p.display()}\t{p.key()}")
    return EXIT_OK


def cmd_bookmark(ctx: Context) -> int:
    a = ctx.args
    svc = ctx.service
    store = svc.user
    action = a.action or "list"
    if action == "add":
        if not a.args:
            raise CLIError("Give a reference to bookmark, e.g. 'qbible bookmark add John 3:16'.")
        tid = svc.pack(a.translation).id
        p = svc.resolve(_join(a.args), tid)
        bm, created = store.add_bookmark(tid, p.reference, a.label or "")
        if created:
            ctx.note(f"Bookmarked {bm.reference.display()} (id {bm.id}).")
        else:
            ctx.note(f"{bm.reference.display()} is already bookmarked (id {bm.id})"
                     + ("; label updated." if a.label else "."))
        return EXIT_OK
    if action in ("remove", "rm", "delete"):
        if len(a.args) != 1 or not a.args[0].isdigit():
            raise CLIError("Give the bookmark id to remove (see 'qbible bookmark list').")
        store.remove_bookmark(int(a.args[0]))
        ctx.note(f"Removed bookmark {a.args[0]}.")
        return EXIT_OK
    if action == "label":
        if len(a.args) < 1 or not a.args[0].isdigit():
            raise CLIError("Usage: qbible bookmark label ID TEXT")
        bm = store.update_bookmark_label(int(a.args[0]), " ".join(a.args[1:]))
        ctx.note(f"Bookmark {bm.id} label set.")
        return EXIT_OK
    if action == "open":
        if len(a.args) != 1 or not a.args[0].isdigit():
            raise CLIError("Usage: qbible bookmark open ID")
        bid = int(a.args[0])
        bm = next((b for b in store.bookmarks() if b.id == bid), None)
        if bm is None:
            raise NotFoundError(f"No bookmark with id {bid}.")
        view = svc.passage(bm.reference, bm.translation)
        return show_passage(ctx, view, record=True)
    if action != "list":
        raise CLIError(f"Unknown bookmark action '{action}'. Use add, list, open, label or remove.")
    items = store.bookmarks()
    if a.json:
        ctx.json([b.to_dict() for b in items])
        return EXIT_OK
    if not items:
        ctx.note("No bookmarks yet. Add one with 'qbible bookmark add John 3:16 --label \"...\"'.")
        return EXIT_OK
    for b in items:
        label = f"  {b.label}" if b.label else ""
        ctx.print(f"{b.id:>4}  {ctx.style.ref(b.reference.display())} ({b.translation.upper()}){label}")
    return EXIT_OK


def cmd_history(ctx: Context) -> int:
    a = ctx.args
    store = ctx.service.user
    if a.action == "clear":
        n = store.clear_history()
        ctx.note(f"Cleared {n} history entr{'y' if n == 1 else 'ies'}.")
        return EXIT_OK
    items = store.history(a.limit)
    if a.json:
        ctx.json([h.to_dict() for h in items])
        return EXIT_OK
    if not items:
        ctx.note("Reading history is empty.")
        return EXIT_OK
    for h in items:
        when = h.opened_at.replace("T", " ")[:16]
        ctx.print(f"{ctx.style.dim(when)}  {h.reference.display()} ({h.translation.upper()})")
    return EXIT_OK


def cmd_translations(ctx: Context) -> int:
    svc = ctx.service
    items = svc.translations()
    if ctx.args.json:
        ctx.json(items)
        return EXIT_OK
    if not items:
        raise DataError("No translations installed.")
    for t in items:
        default = " (default)" if t["id"] == svc.default_translation else ""
        ctx.print(f"{t['id']:<8} {t['name']}{default}")
        ctx.print(f"         {t['verse_count']} verses; licence: {t['licence']}")
        if t["attribution"]:
            ctx.print(f"         {t['attribution']}")
        if t["source_url"]:
            ctx.print(f"         Source: {t['source_url']}")
    for p in svc.repo.problems:
        ctx.note(f"qbible: warning: {p}")
    return EXIT_OK


def cmd_import(ctx: Context) -> int:
    from .importer import TranslationInfo, import_file
    from .validation import validate_pack

    a = ctx.args
    tid = a.id.lower()
    existing = ctx.service.repo.packs.get(tid)
    dest = ctx.locs.user_translations / f"{tid}.sqlite"
    if existing and not (a.force and existing.path.resolve() == dest.resolve()):
        raise CLIError(
            f"A translation with id '{tid}' is already installed at {existing.path}. "
            "Choose another id" + (" (only user-imported translations can be replaced)." if a.force else
                                   ", or use --force to replace your own import."),
            EXIT_DATA,
        )
    info = TranslationInfo(
        id=tid, name=a.name, abbreviation=a.abbreviation or tid.upper(), language=a.language,
        licence=a.licence, copyright=a.copyright or "", attribution=a.attribution or "",
        source_name=a.source_name or "", source_url=a.source_url or "",
        retrieved=a.retrieved or "", versification=a.versification or "",
    )
    result = import_file(Path(a.file), a.format, info, dest, overwrite=a.force)
    ctx.note(f"Imported {result.verse_count} verses in {result.book_count} books to {result.path}")
    if result.excluded:
        ctx.note("Excluded non-canonical books: " + ", ".join(result.excluded))
    report = validate_pack(result.path)
    ctx.print(report.to_text().rstrip())
    if not report.ok:
        result.path.unlink()
        ctx.note("Validation failed; the import was removed.")
        return EXIT_DATA
    return EXIT_OK


def cmd_remove_translation(ctx: Context) -> int:
    tid = ctx.args.id.lower()
    pack = ctx.service.repo.get(tid)
    user_dir = ctx.locs.user_translations.resolve()
    if pack.path.resolve().parent != user_dir:
        raise CLIError(f"'{tid}' is not a user-imported translation ({pack.path}); it cannot be removed here.",
                       EXIT_DATA)
    pack.path.unlink()
    ctx.note(f"Removed translation '{tid}'.")
    return EXIT_OK


def cmd_validate(ctx: Context) -> int:
    from .validation import validate_pack

    pack = ctx.service.pack(ctx.args.translation)
    report = validate_pack(pack.path)
    if ctx.args.json:
        ctx.json(report.to_dict())
    else:
        ctx.print(report.to_text().rstrip())
    return EXIT_OK if report.ok else EXIT_DATA


def cmd_paths(ctx: Context) -> int:
    d = ctx.locs.as_dict()
    d["translation_search_path"] = os.pathsep.join(str(p) for p in ctx.locs.translation_dirs())
    if ctx.args.json:
        ctx.json(d)
    else:
        for k, v in d.items():
            ctx.print(f"{k:<24} {v}")
    return EXIT_OK


def cmd_config(ctx: Context) -> int:
    a = ctx.args
    cfg = ctx.config
    if a.action == "list" or a.action is None:
        for name, s in SETTINGS.items():
            choices = f" [{'|'.join(s.choices)}]" if s.choices else (" [true|false]" if s.kind == "bool" else "")
            ctx.print(f"{name:<22} {cfg.get(name):<10} {ctx.style.dim(s.help + choices)}")
        ctx.note(f"Configuration file: {cfg.path}")
        return EXIT_OK
    if not a.key:
        raise CLIError(f"'qbible config {a.action}' needs a setting name.")
    if a.key not in SETTINGS:
        raise CLIError(f"Unknown setting '{a.key}'. Run 'qbible config list'.")
    if a.action == "get":
        ctx.print(cfg.get(a.key))
    elif a.action == "set":
        if a.value is None:
            raise CLIError("Usage: qbible config set KEY VALUE")
        ctx.note(f"{a.key} = {cfg.set(a.key, a.value)}")
    elif a.action == "unset":
        cfg.unset(a.key)
        ctx.note(f"{a.key} reset to default ({SETTINGS[a.key].default}).")
    return EXIT_OK


def cmd_serve(ctx: Context) -> int:
    from .server import is_loopback, serve

    a = ctx.args
    host = a.host or ctx.config.get("server.host")
    port = a.port if a.port is not None else ctx.config.get_int("server.port")
    exit_when_closed = ctx.config.get_bool("server.exit_when_closed")
    if a.exit_when_closed is not None:
        exit_when_closed = a.exit_when_closed
    if exit_when_closed and not is_loopback(host):
        # A shared server must not stop when one visitor closes a page (or be
        # stopped deliberately by one).
        if a.exit_when_closed:
            raise CLIError("--exit-when-closed is only available on a loopback address.")
        exit_when_closed = False
    return serve(ctx.service, ctx.locs, host=host, port=port, open_browser=a.open,
                 allow_remote=a.allow_remote, user_data=not a.no_user_data,
                 exit_when_closed=exit_when_closed, watchdog_timeouts=_watchdog_timeouts(),
                 out=ctx.err)


def _watchdog_timeouts() -> dict | None:
    """``QBIBLE_WATCHDOG_TIMEOUTS=visible,hidden,grace[,startup]`` (seconds) — for tests and tuning."""
    raw = os.environ.get("QBIBLE_WATCHDOG_TIMEOUTS")
    if not raw:
        return None
    usage = "QBIBLE_WATCHDOG_TIMEOUTS must be visible,hidden,grace[,startup] in seconds"
    try:
        values = [float(x) for x in raw.split(",")]
    except ValueError:
        raise CLIError(usage) from None
    if len(values) not in (3, 4):
        raise CLIError(usage)
    visible, hidden, grace = values[:3]
    if not (0 < grace <= visible <= hidden) or (len(values) == 4 and values[3] <= 0):
        raise CLIError("QBIBLE_WATCHDOG_TIMEOUTS must satisfy 0 < grace <= visible <= hidden, startup > 0")
    out = {"visible_timeout": visible, "hidden_timeout": hidden, "close_grace": grace}
    if len(values) == 4:
        out["startup_allowance"] = values[3]
    return out


def cmd_shell(ctx: Context) -> int:
    from .interactive import Shell

    Shell(ctx).cmdloop()
    return EXIT_OK


def cmd_completion(ctx: Context) -> int:
    from .completion import BASH_COMPLETION

    ctx.out.write(BASH_COMPLETION)
    return EXIT_OK


# --------------------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    # Options accepted both before and after the command name.
    common = argparse.ArgumentParser(add_help=False)
    g = common.add_argument_group("global options")
    g.add_argument("-t", "--translation", metavar="ID", default=argparse.SUPPRESS,
                   help="translation id (default: kjv; see 'qbible translations')")
    g.add_argument("--colour", "--color", dest="colour", choices=("auto", "always", "never"),
                   default=argparse.SUPPRESS, help="use colour: auto (default), always or never")
    g.add_argument("--plain", "--no-colour", "--no-color", dest="plain", action="store_true",
                   default=argparse.SUPPRESS, help="plain text: no colour or terminal formatting")

    reading = argparse.ArgumentParser(add_help=False)
    r = reading.add_argument_group("reading options")
    nums = r.add_mutually_exclusive_group()
    nums.add_argument("-n", "--numbers", action="store_true", help="show verse numbers")
    nums.add_argument("-N", "--no-numbers", action="store_true", help="hide verse numbers")
    r.add_argument("--supplied", choices=("plain", "brackets", "italic"),
                   help="how to show words supplied by the translators (default: italic in colour "
                        "terminals, otherwise plain)")
    r.add_argument("--pilcrows", action="store_true", help="show ¶ paragraph marks")
    r.add_argument("--no-heading", action="store_true", help="omit the reference heading")
    r.add_argument("--no-wrap", action="store_true", help="do not wrap long lines in a terminal")
    r.add_argument("--no-history", action="store_true", help="do not update the reading position/history")
    r.add_argument("--json", action="store_true", help="output JSON")

    p = argparse.ArgumentParser(
        prog="qbible",
        description="qbible — a modern, ad-free Bible reader (King James Version).",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[common],
    )
    p.add_argument("-V", "--version", action="version", version=f"qbible {__version__}")
    sub = p.add_subparsers(dest="command", metavar="COMMAND", title="commands")

    def add(name, help_, parents=(), aliases=(), **kw):
        sp = sub.add_parser(name, help=help_, description=help_, parents=[common, *parents],
                            aliases=list(aliases), **kw)
        return sp

    sp = add("read", "read a verse, range, chapter or book", [reading])
    sp.add_argument("reference", nargs="+", help="e.g. John 3:16, 'Psalm 23', Rev 21:1-4")
    sp.set_defaults(func=cmd_read)

    sp = add("chapter", "read a whole chapter (e.g. 'chapter John 3')", [reading])
    sp.add_argument("reference", nargs="+", help="book and chapter")
    sp.set_defaults(func=cmd_chapter)

    for name, step, aliases in (("next", 1, ()), ("previous", -1, ("prev",))):
        sp = add(name, f"read the {name} chapter after your last reading position"
                 if step > 0 else "read the chapter before your last reading position",
                 [reading], aliases)
        sp.add_argument("--from", dest="start", nargs="+", metavar="REFERENCE",
                        help="start from this reference instead of the saved position")
        sp.set_defaults(func=lambda ctx, s=step: cmd_step(ctx, s))

    sp = add("random", "show a random verse", [reading])
    sp.add_argument("--testament", choices=("OT", "NT"), type=str.upper)
    sp.set_defaults(func=cmd_random)

    sp = add("books", "list the books of the Bible")
    sp.add_argument("--testament", choices=("OT", "NT"), type=str.upper)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_books)

    sp = add("search", "search for words or an exact phrase", [reading],
             epilog='A quoted argument is an exact phrase: qbible search "faith without works".\n'
                    'Several unquoted words must all appear: qbible search faith hope.\n'
                    'Inside one argument you may combine: qbible search \'"fear not" -afraid lord*\'.',
             formatter_class=argparse.RawDescriptionHelpFormatter)
    sp.add_argument("query", nargs="+", help="words or a quoted phrase")
    m = sp.add_mutually_exclusive_group()
    m.add_argument("--phrase", action="store_true", help="treat all words as one exact phrase")
    m.add_argument("--words", action="store_true", help="require all words, in any order")
    m.add_argument("--any", action="store_true", help="match any of the words")
    sp.add_argument("-l", "--limit", type=int, metavar="N", help="results per page (default 20, max 500)")
    sp.add_argument("-p", "--page", type=int, default=1, metavar="N", help="page of results (default 1)")
    sp.add_argument("-c", "--context", type=int, nargs="?", const=1, default=0, metavar="N",
                    help="show N surrounding verses (default 1 when given)")
    sp.add_argument("--sort", choices=SORTS, default="canonical",
                    help="canonical (Bible order, default) or relevance")
    sp.add_argument("--book", metavar="BOOK", help="only search this book")
    sp.add_argument("--testament", choices=("OT", "NT"), type=str.upper, help="only search one testament")
    sp.add_argument("--count", action="store_true", help="print only the number of matching verses")
    sp.set_defaults(func=cmd_search)

    sp = add("ref", "check and normalise a scripture reference")
    sp.add_argument("reference", nargs="+")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_ref)

    sp = add("bookmark", "manage bookmarks: add, list, open, label, remove", aliases=("bookmarks",),
             epilog="examples:\n  qbible bookmark add John 3:16 --label \"God's love\"\n"
                    "  qbible bookmark list\n  qbible bookmark open 3\n  qbible bookmark remove 3",
             formatter_class=argparse.RawDescriptionHelpFormatter, parents=[reading])
    sp.add_argument("action", nargs="?", choices=("add", "list", "open", "label", "remove", "rm", "delete"))
    sp.add_argument("args", nargs="*", help="reference (add) or bookmark id")
    sp.add_argument("--label", help="descriptive label for 'add'")
    sp.set_defaults(func=cmd_bookmark)

    sp = add("history", "show or clear reading history")
    sp.add_argument("action", nargs="?", choices=("list", "clear"), default="list")
    sp.add_argument("--limit", type=int, default=20)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_history)

    sp = add("shell", "interactive reading mode", aliases=("interactive",))
    sp.set_defaults(func=cmd_shell)

    sp = add("serve", "start the browser interface (local only by default)")
    sp.add_argument("--host", help="address to listen on (default 127.0.0.1)")
    sp.add_argument("--port", type=int, help="port (default 8737; 0 picks a free port)")
    sp.add_argument("--open", action="store_true", help="open the web browser")
    sp.add_argument("--allow-remote", action="store_true",
                    help="permit listening on a non-loopback address (see docs/DEPLOYMENT.md)")
    sp.add_argument("--no-user-data", action="store_true",
                    help="disable server-side bookmarks/history (browser keeps its own)")
    w = sp.add_mutually_exclusive_group()
    w.add_argument("--exit-when-closed", dest="exit_when_closed", action="store_true", default=None,
                   help="stop when all qbible browser pages are closed (default; "
                        "config: server.exit_when_closed)")
    w.add_argument("--keep-running", dest="exit_when_closed", action="store_false",
                   help="keep running after pages are closed (use for shared or public servers)")
    sp.set_defaults(func=cmd_serve)

    sp = add("translations", "list installed translations")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_translations)

    sp = add("import", "import another legally obtained translation")
    sp.add_argument("file", help="source file (.txt/.zip for vpl, .tsv for tsv)")
    sp.add_argument("--id", required=True, help="short id, e.g. 'web'")
    sp.add_argument("--name", required=True, help="full name")
    sp.add_argument("--licence", "--license", dest="licence", required=True,
                    help="licence or permission under which you may use the text")
    sp.add_argument("--format", choices=("vpl", "tsv"), default="tsv")
    sp.add_argument("--abbreviation")
    sp.add_argument("--language", default="en")
    sp.add_argument("--copyright")
    sp.add_argument("--attribution")
    sp.add_argument("--source-name")
    sp.add_argument("--source-url")
    sp.add_argument("--retrieved", help="date the source was obtained (YYYY-MM-DD)")
    sp.add_argument("--versification", help="set to 'kjv' to validate strictly against KJV versification")
    sp.add_argument("--force", action="store_true", help="replace your own earlier import with this id")
    sp.set_defaults(func=cmd_import)

    sp = add("remove-translation", "remove a translation you imported")
    sp.add_argument("id")
    sp.set_defaults(func=cmd_remove_translation)

    sp = add("validate", "check a translation's integrity and completeness")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_validate)

    sp = add("config", "show or change settings")
    sp.add_argument("action", nargs="?", choices=("list", "get", "set", "unset"), default="list")
    sp.add_argument("key", nargs="?")
    sp.add_argument("value", nargs="?")
    sp.set_defaults(func=cmd_config)

    sp = add("paths", "show where qbible reads and stores files")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_paths)

    sp = add("completion", "print the bash completion script")
    sp.add_argument("shell", nargs="?", choices=("bash",), default="bash")
    sp.set_defaults(func=cmd_completion)

    return p


def main(argv: list[str] | None = None, out=None, err=None) -> int:
    parser = build_parser()
    argv = sys.argv[1:] if argv is None else argv
    err = err or sys.stderr
    try:
        with contextlib.redirect_stdout(out or sys.stdout), contextlib.redirect_stderr(err):
            args = parser.parse_args(argv)
    except SystemExit as e:  # argparse: --help/--version (0) or usage error (2)
        _flush_stdout_quietly()
        return int(e.code or 0)
    for attr, default in (("translation", None), ("colour", None), ("plain", False)):
        if not hasattr(args, attr):
            setattr(args, attr, default)
    if not getattr(args, "command", None):
        parser.print_help(out or sys.stdout)
        return EXIT_OK

    try:
        ctx = Context(args, out, err)
        return args.func(ctx)
    except CLIError as e:
        print(f"qbible: {e}", file=err)
        return e.code
    except (ReferenceError_, NotFoundError) as e:
        print(f"qbible: {e}", file=err)
        return EXIT_REFERENCE
    except SearchQueryError as e:
        print(f"qbible: {e}", file=err)
        return EXIT_USAGE
    except (DataError, TranslationNotFoundError, UserDataError) as e:
        print(f"qbible: {e}", file=err)
        return EXIT_DATA
    except QBibleError as e:
        print(f"qbible: {e}", file=err)
        return EXIT_USAGE
    except KeyboardInterrupt:
        print("", file=err)
        return EXIT_INTERRUPTED
    except BrokenPipeError:
        _discard_stdout()
        return EXIT_OK
    finally:
        _flush_stdout_quietly()


def _discard_stdout() -> None:
    """Output was piped to a program that stopped reading (e.g. head): send the
    rest to /dev/null so Python does not complain when it flushes at exit."""
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
    except (OSError, ValueError):
        pass


def _flush_stdout_quietly() -> None:
    try:
        sys.stdout.flush()
    except BrokenPipeError:
        _discard_stdout()
    except (OSError, ValueError):
        pass

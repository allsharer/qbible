"""Interactive terminal reading session (``qbible shell``).

The session keeps its own current position, starting from the saved reading
position if there is one. Every passage opened is recorded in the history,
so 'qbible next' outside the session continues from the same place.
"""

from __future__ import annotations

import cmd
import shlex

from .errors import QBibleError
from .reference import Reference, chapter_reference
from .termfmt import format_passage, format_segments

HELP = """\
Commands (unambiguous prefixes work, e.g. 'n', 's faith'):
  <reference>          open a passage, e.g.  John 3:16   Ps 23   Rom 8:28-39
  <number>             open that chapter of the current book
  n, next              next chapter          p, prev  previous chapter
  s, search WORDS      search ("quotes" for an exact phrase); 'more' for the next page
  b, bookmark [LABEL]  bookmark the current passage
  bookmarks            list bookmarks;  'open ID' opens one
  history              recent passages
  random               a random verse
  where                show the current position
  numbers              toggle verse numbers
  q, quit              leave (Ctrl+D also works)"""


class Shell(cmd.Cmd):
    intro = "qbible interactive reading. Type 'help' for commands, 'q' to quit."
    doc_header = ""

    def __init__(self, ctx):
        super().__init__(stdout=ctx.out)
        self.ctx = ctx
        self.svc = ctx.service
        self.translation = self.svc.pack(ctx.args.translation).id
        self.current: Reference | None = None
        self.numbers = True
        self._search: tuple[str, int] | None = None
        pos = self.svc.user.last_position()
        if pos is not None:
            self.current = pos.reference
            self.intro += f"\nLast position: {pos.reference.display()} — type 'here' to show it, 'n' for the next chapter."
        self._update_prompt()

    # -- helpers ----------------------------------------------------------------
    def _update_prompt(self) -> None:
        where = self.current.display() if self.current else "qbible"
        self.prompt = f"{where}> "

    def _say(self, text: str = "") -> None:
        print(text, file=self.ctx.out)

    def _show(self, ref: Reference) -> None:
        view = self.svc.passage(ref, self.translation)
        opts = self.ctx.read_options()
        opts.numbers = self.numbers
        self._say(format_passage(view.to_dict(), self.ctx.style, opts))
        self.current = view.reference
        try:
            self.svc.user.record(self.translation, view.reference)
        except QBibleError as e:
            self._say(f"(position not saved: {e})")
        self._update_prompt()

    def onecmd(self, line: str) -> bool:
        try:
            return super().onecmd(line)
        except QBibleError as e:
            self._say(str(e))
        except ValueError as e:  # shlex quoting errors
            self._say(f"Could not understand that: {e}")
        return False

    def emptyline(self) -> bool:
        return False

    def default(self, line: str) -> bool:
        text = line.strip()
        if text.lower() in ("q", "quit", "exit"):
            return True
        if text.isdigit() and self.current is not None:
            self._show(chapter_reference(self.current.book, int(text)))
            return False
        self._show(self.svc.parse(text))
        return False

    def completenames(self, text, *ignored):
        return [n for n in super().completenames(text, *ignored) if n not in ("EOF",)]

    # -- commands ---------------------------------------------------------------
    def do_help(self, arg: str) -> bool:
        self._say(HELP)
        return False

    def do_next(self, arg: str) -> bool:
        return self._step(1)

    def do_prev(self, arg: str) -> bool:
        return self._step(-1)

    do_n = do_next
    do_p = do_previous = do_prev

    def _step(self, step: int) -> bool:
        if self.current is None:
            self._say("Open a passage first, e.g. 'John 1'.")
            return False
        target = self.svc.step_from(self.current, step, self.translation)
        if target is None:
            self._say("You are at the " + ("beginning" if step < 0 else "end") + " of the Bible.")
        else:
            self._show(target)
        return False

    def do_here(self, arg: str) -> bool:
        if self.current is None:
            self._say("No current passage.")
        else:
            self._show(self.current)
        return False

    def do_where(self, arg: str) -> bool:
        self._say(self.current.display() if self.current else "No current passage.")
        return False

    def do_search(self, arg: str) -> bool:
        if not arg.strip():
            self._say("Usage: search WORDS   (use quotes for an exact phrase)")
            return False
        self._search = (arg, 0)
        self._run_search()
        return False

    do_s = do_search

    def do_more(self, arg: str) -> bool:
        if not self._search:
            self._say("No search to continue.")
            return False
        q, offset = self._search
        self._search = (q, offset + 20)
        self._run_search()
        return False

    def _run_search(self) -> None:
        q, offset = self._search
        result = self.svc.search(q, self.translation, limit=20, offset=offset)
        data = self.svc.search_dict(result, self.translation)
        if not result.total:
            self._say("No matches.")
            return
        supplied = self.ctx.read_options().supplied
        for r in data["results"]:
            self._say(f"{self.ctx.style.ref(r['reference']['display'])}  "
                      f"{format_segments(r['segments'], self.ctx.style, supplied)}")
        shown = offset + len(result.hits)
        tail = " Type 'more' for the next page." if result.has_more else ""
        self._say(self.ctx.style.dim(f"{result.total} matches; showing {offset + 1}-{shown}.{tail}"))

    def do_bookmark(self, arg: str) -> bool:
        if self.current is None:
            self._say("Open a passage first.")
            return False
        bm, created = self.svc.user.add_bookmark(self.translation, self.current, arg.strip())
        self._say(("Bookmarked " if created else "Already bookmarked: ") + f"{bm.reference.display()} (id {bm.id})")
        return False

    do_b = do_bookmark

    def do_bookmarks(self, arg: str) -> bool:
        items = self.svc.user.bookmarks()
        if not items:
            self._say("No bookmarks yet. Use 'bookmark [label]' to add the current passage.")
        for b in items:
            self._say(f"{b.id:>4}  {b.reference.display()}" + (f"  {b.label}" if b.label else ""))
        return False

    def do_open(self, arg: str) -> bool:
        parts = shlex.split(arg)
        if len(parts) != 1 or not parts[0].isdigit():
            self._say("Usage: open BOOKMARK-ID")
            return False
        bid = int(parts[0])
        bm = next((b for b in self.svc.user.bookmarks() if b.id == bid), None)
        if bm is None:
            self._say(f"No bookmark with id {bid}.")
        else:
            self._show(bm.reference)
        return False

    def do_history(self, arg: str) -> bool:
        for h in self.svc.user.history(15):
            self._say(f"  {h.reference.display()}")
        return False

    def do_random(self, arg: str) -> bool:
        view = self.svc.random_verse(self.translation)
        self._show(view.reference)
        return False

    def do_numbers(self, arg: str) -> bool:
        if arg.strip():  # "Numbers 6:24" is the book, not the toggle
            return self.default(f"Numbers {arg}")
        self.numbers = not self.numbers
        self._say("Verse numbers " + ("on." if self.numbers else "off."))
        return False

    def do_quit(self, arg: str) -> bool:
        return True

    do_q = do_exit = do_quit

    def do_EOF(self, arg: str) -> bool:
        self._say()
        return True

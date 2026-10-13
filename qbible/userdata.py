"""Per-user data: bookmarks and reading history.

Stored in a SQLite database separate from the (read-only) Bible text, by
default ``$XDG_DATA_HOME/qbible/user.sqlite``. Each operating-system user has
their own file.

References are stored as stable reference keys (``JHN.3.16``) plus the
translation id, never as copied Bible text, so user data never duplicates or
modifies scripture.

Schema changes are applied by numbered, explicit migrations recorded in
``schema_migrations``. A database created by a *newer* qbible is refused
rather than modified. The :class:`UserStore` interface is the seam where a
future synchronisation backend could be introduced.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .errors import NotFoundError, UserDataError
from .reference import Reference, parse_key

MAX_HISTORY = 200
MAX_LABEL = 200

MIGRATIONS: list[tuple[int, str, str]] = [
    (
        1,
        "bookmarks and reading history",
        """
        CREATE TABLE bookmarks (
            id          INTEGER PRIMARY KEY,
            translation TEXT NOT NULL,
            ref_key     TEXT NOT NULL,
            label       TEXT NOT NULL DEFAULT '',
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL,
            UNIQUE (translation, ref_key)
        );
        CREATE TABLE history (
            id          INTEGER PRIMARY KEY,
            translation TEXT NOT NULL,
            ref_key     TEXT NOT NULL,
            opened_at   TEXT NOT NULL
        );
        CREATE INDEX history_opened ON history (opened_at DESC, id DESC);
        """,
    ),
]
LATEST_VERSION = MIGRATIONS[-1][0]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Bookmark:
    id: int
    translation: str
    reference: Reference
    label: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "translation": self.translation,
            "key": self.reference.key(),
            "reference": self.reference.display(),
            "label": self.label,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class HistoryEntry:
    id: int
    translation: str
    reference: Reference
    opened_at: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "translation": self.translation,
            "key": self.reference.key(),
            "reference": self.reference.display(),
            "opened_at": self.opened_at,
        }


def schema_version(conn: sqlite3.Connection) -> int:
    has = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    ).fetchone()
    if not has:
        return 0
    (v,) = conn.execute("SELECT coalesce(max(version), 0) FROM schema_migrations").fetchone()
    return v


def migrate(conn: sqlite3.Connection, target: int = LATEST_VERSION) -> list[int]:
    """Apply pending migrations up to ``target``; return the versions applied."""
    current = schema_version(conn)
    if current > LATEST_VERSION:
        raise UserDataError(
            f"The user database was created by a newer qbible (schema {current}); "
            f"this version understands up to {LATEST_VERSION}. Upgrade qbible."
        )
    applied = []
    with conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version INTEGER PRIMARY KEY, description TEXT NOT NULL, applied_at TEXT NOT NULL)"
        )
    for version, description, sql in MIGRATIONS:
        if current < version <= target:
            try:
                conn.execute("BEGIN IMMEDIATE")  # serialise with other processes
                if schema_version(conn) >= version:
                    conn.execute("COMMIT")
                    continue
                for stmt in sql.split(";"):
                    if stmt.strip():
                        conn.execute(stmt)
                conn.execute(
                    "INSERT INTO schema_migrations (version, description, applied_at) VALUES (?, ?, ?)",
                    (version, description, _now()),
                )
                conn.execute("COMMIT")
            except sqlite3.Error as e:
                conn.execute("ROLLBACK")
                raise UserDataError(f"Migration {version} failed: {e}") from None
            applied.append(version)
    return applied


class UserStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            new = not self.path.exists()
            conn = sqlite3.connect(self.path, timeout=5, isolation_level=None)
            if new:
                os.chmod(self.path, 0o600)
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA busy_timeout = 5000")
            migrate(conn)
            return conn
        except (sqlite3.Error, OSError) as e:
            raise UserDataError(f"Cannot open user data at {self.path}: {e}") from None

    # -- bookmarks ----------------------------------------------------------------
    def add_bookmark(self, translation: str, ref: Reference, label: str = "") -> tuple[Bookmark, bool]:
        """Add a bookmark. Returns ``(bookmark, created)``; an existing bookmark
        for the same passage is returned (with its label updated if one is given)."""
        label = (label or "").strip()
        if len(label) > MAX_LABEL:
            raise UserDataError(f"Bookmark labels are limited to {MAX_LABEL} characters.")
        conn = self._connect()
        try:
            now = _now()
            key = ref.key()
            row = conn.execute(
                "SELECT id FROM bookmarks WHERE translation = ? AND ref_key = ?", (translation, key)
            ).fetchone()
            if row:
                if label:
                    conn.execute("UPDATE bookmarks SET label = ?, updated_at = ? WHERE id = ?",
                                 (label, now, row[0]))
                return self._get_bookmark(conn, row[0]), False
            cur = conn.execute(
                "INSERT INTO bookmarks (translation, ref_key, label, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (translation, key, label, now, now),
            )
            return self._get_bookmark(conn, cur.lastrowid), True
        finally:
            conn.close()

    def _get_bookmark(self, conn: sqlite3.Connection, bid: int) -> Bookmark:
        row = conn.execute(
            "SELECT id, translation, ref_key, label, created_at, updated_at FROM bookmarks WHERE id = ?",
            (bid,),
        ).fetchone()
        if not row:
            raise NotFoundError(f"No bookmark with id {bid}.")
        return Bookmark(row[0], row[1], parse_key(row[2]), row[3], row[4], row[5])

    def bookmarks(self) -> list[Bookmark]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT id, translation, ref_key, label, created_at, updated_at FROM bookmarks "
                "ORDER BY created_at DESC, id DESC"
            ).fetchall()
        finally:
            conn.close()
        out = []
        for r in rows:
            try:
                out.append(Bookmark(r[0], r[1], parse_key(r[2]), r[3], r[4], r[5]))
            except Exception:
                continue  # skip a corrupt row rather than failing the whole list
        return out

    def find_bookmark(self, translation: str, ref: Reference) -> Bookmark | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT id FROM bookmarks WHERE translation = ? AND ref_key = ?",
                (translation, ref.key()),
            ).fetchone()
            return self._get_bookmark(conn, row[0]) if row else None
        finally:
            conn.close()

    def update_bookmark_label(self, bid: int, label: str) -> Bookmark:
        label = (label or "").strip()
        if len(label) > MAX_LABEL:
            raise UserDataError(f"Bookmark labels are limited to {MAX_LABEL} characters.")
        conn = self._connect()
        try:
            cur = conn.execute("UPDATE bookmarks SET label = ?, updated_at = ? WHERE id = ?",
                               (label, _now(), bid))
            if cur.rowcount == 0:
                raise NotFoundError(f"No bookmark with id {bid}.")
            return self._get_bookmark(conn, bid)
        finally:
            conn.close()

    def remove_bookmark(self, bid: int) -> None:
        conn = self._connect()
        try:
            cur = conn.execute("DELETE FROM bookmarks WHERE id = ?", (bid,))
            if cur.rowcount == 0:
                raise NotFoundError(f"No bookmark with id {bid}.")
        finally:
            conn.close()

    # -- history ------------------------------------------------------------------
    def record(self, translation: str, ref: Reference) -> None:
        """Record that a passage was opened (moves an existing entry to the top)."""
        conn = self._connect()
        try:
            key = ref.key()
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM history WHERE translation = ? AND ref_key = ?", (translation, key))
            conn.execute("INSERT INTO history (translation, ref_key, opened_at) VALUES (?, ?, ?)",
                         (translation, key, _now()))
            conn.execute(
                "DELETE FROM history WHERE id NOT IN "
                "(SELECT id FROM history ORDER BY id DESC LIMIT ?)",
                (MAX_HISTORY,),
            )
            conn.execute("COMMIT")
        finally:
            conn.close()

    def history(self, limit: int = 20) -> list[HistoryEntry]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT id, translation, ref_key, opened_at FROM history ORDER BY id DESC LIMIT ?",
                (max(1, min(limit, MAX_HISTORY)),),
            ).fetchall()
        finally:
            conn.close()
        out = []
        for r in rows:
            try:
                out.append(HistoryEntry(r[0], r[1], parse_key(r[2]), r[3]))
            except Exception:
                continue
        return out

    def last_position(self) -> HistoryEntry | None:
        h = self.history(1)
        return h[0] if h else None

    def clear_history(self) -> int:
        conn = self._connect()
        try:
            return conn.execute("DELETE FROM history").rowcount
        finally:
            conn.close()

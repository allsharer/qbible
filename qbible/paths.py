"""File locations.

Defaults follow the XDG Base Directory specification. Every location can be
overridden with an environment variable, which is how the test-suite and
development runs keep away from real user data.

=========================  ==============================================  ==========================
What                       Default                                         Override
=========================  ==============================================  ==========================
Installed shared data      ``<prefix>/share/qbible`` (read-only)           ``QBIBLE_SHARE_DIR``
Bundled translations       ``<share>/translations/*.sqlite``               ``QBIBLE_TRANSLATIONS_PATH``
Browser assets             ``<share>/web``                                 ``QBIBLE_WEB_DIR``
User data (bookmarks …)    ``$XDG_DATA_HOME/qbible/user.sqlite``           ``QBIBLE_DATA_HOME``
User-imported translations ``$XDG_DATA_HOME/qbible/translations``          ``QBIBLE_DATA_HOME``
Configuration              ``$XDG_CONFIG_HOME/qbible/config.ini``          ``QBIBLE_CONFIG_HOME``
=========================  ==============================================  ==========================

``QBIBLE_TRANSLATIONS_PATH`` is a ``:``-separated list searched *before* the
user and shared translation directories.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent


def _env_path(name: str) -> Path | None:
    v = os.environ.get(name)
    return Path(v).expanduser() if v else None


def _xdg(name: str, fallback: str) -> Path:
    v = os.environ.get(name)
    if v and os.path.isabs(v):
        return Path(v)
    return Path.home() / fallback


def share_dir() -> Path:
    """Directory holding read-only application data.

    Installed layout: ``<share>/python/qbible/`` (this package) next to
    ``<share>/web`` and ``<share>/translations``. Source-tree layout: the
    repository, with built translations in ``build/translations``.
    """
    env = _env_path("QBIBLE_SHARE_DIR")
    if env:
        return env
    parent = PACKAGE_DIR.parent
    if parent.name == "python" and (parent.parent / "web").is_dir():
        return parent.parent
    return parent


def _is_source_tree(share: Path) -> bool:
    return (share / "qbible" / "__init__.py").is_file()


@dataclass(frozen=True)
class Locations:
    share: Path
    web: Path
    shared_translations: Path
    data_home: Path
    config_home: Path
    extra_translation_dirs: tuple[Path, ...]

    @property
    def user_db(self) -> Path:
        return self.data_home / "user.sqlite"

    @property
    def user_translations(self) -> Path:
        return self.data_home / "translations"

    @property
    def config_file(self) -> Path:
        return self.config_home / "config.ini"

    def translation_dirs(self) -> list[Path]:
        """Search order for translation packs (first match for an id wins)."""
        dirs = [*self.extra_translation_dirs, self.user_translations, self.shared_translations]
        seen, out = set(), []
        for d in dirs:
            r = d.resolve() if d.exists() else d
            if r not in seen:
                seen.add(r)
                out.append(d)
        return out

    def as_dict(self) -> dict[str, str]:
        return {
            "share": str(self.share),
            "web": str(self.web),
            "shared_translations": str(self.shared_translations),
            "user_translations": str(self.user_translations),
            "extra_translation_dirs": os.pathsep.join(str(p) for p in self.extra_translation_dirs),
            "user_db": str(self.user_db),
            "config_file": str(self.config_file),
        }


def locations() -> Locations:
    share = share_dir()
    source = _is_source_tree(share)
    shared_tr = share / ("build/translations" if source else "translations")
    extra = tuple(
        Path(p).expanduser()
        for p in os.environ.get("QBIBLE_TRANSLATIONS_PATH", "").split(os.pathsep)
        if p
    )
    return Locations(
        share=share,
        web=_env_path("QBIBLE_WEB_DIR") or share / "web",
        shared_translations=shared_tr,
        data_home=_env_path("QBIBLE_DATA_HOME") or _xdg("XDG_DATA_HOME", ".local/share") / "qbible",
        config_home=_env_path("QBIBLE_CONFIG_HOME") or _xdg("XDG_CONFIG_HOME", ".config") / "qbible",
        extra_translation_dirs=extra,
    )

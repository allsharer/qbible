"""qbible — a modern, ad-free Bible reader.

The package is organised in layers:

* ``books``, ``reference``, ``textfmt`` — translation-independent rules
  (canonical books, scripture reference parsing, verse text formatting).
* ``repository`` — read-only access to translation packs (SQLite files).
* ``search`` — query parsing and full-text search over a translation pack.
* ``userdata`` — per-user bookmarks, reading history and preferences.
* ``services`` — the application service used by every interface.
* ``cli``, ``interactive``, ``server`` — user interfaces.
"""

__version__ = "1.2.0"
APP_NAME = "qbible"

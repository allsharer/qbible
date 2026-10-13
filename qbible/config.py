"""User configuration stored in ``config.ini`` (see :mod:`qbible.paths`).

Only known keys are accepted; unknown keys in the file are ignored with a
warning rather than silently changing behaviour. The file is optional.
"""

from __future__ import annotations

import configparser
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from .errors import QBibleError


@dataclass(frozen=True)
class Setting:
    section: str
    key: str
    default: str
    choices: tuple[str, ...] = ()
    kind: str = "str"  # str | bool | int
    help: str = ""


SETTINGS: dict[str, Setting] = {
    s.section + "." + s.key: s
    for s in [
        Setting("reading", "translation", "kjv", help="Default translation id"),
        Setting("reading", "verse_numbers", "true", kind="bool", help="Show verse numbers"),
        Setting("reading", "supplied", "auto", ("auto", "plain", "brackets", "italic"),
                help="How to show translator-supplied words ([ ] in the source)"),
        Setting("reading", "pilcrows", "false", kind="bool", help="Show ¶ paragraph marks"),
        Setting("display", "colour", "auto", ("auto", "always", "never"), help="Terminal colour"),
        Setting("search", "limit", "20", kind="int", help="Default number of search results"),
        Setting("server", "host", "127.0.0.1", help="Address the browser server listens on"),
        Setting("server", "port", "8737", kind="int", help="Port the browser server listens on"),
        Setting("server", "exit_when_closed", "true", kind="bool",
                help="Stop 'qbible serve' when all its browser pages are closed"),
    ]
}


def _validate(setting: Setting, value: str) -> str:
    v = value.strip()
    if setting.choices and v not in setting.choices:
        raise QBibleError(f"{setting.section}.{setting.key} must be one of: {', '.join(setting.choices)}")
    if setting.kind == "bool":
        lv = v.lower()
        if lv in ("1", "true", "yes", "on"):
            return "true"
        if lv in ("0", "false", "no", "off"):
            return "false"
        raise QBibleError(f"{setting.section}.{setting.key} must be true or false")
    if setting.kind == "int":
        try:
            n = int(v)
        except ValueError:
            raise QBibleError(f"{setting.section}.{setting.key} must be a whole number") from None
        if n < 1 or n > 65535:
            raise QBibleError(f"{setting.section}.{setting.key} is out of range")
        return str(n)
    return v


class Config:
    def __init__(self, path: Path):
        self.path = path
        self._cp = configparser.ConfigParser(interpolation=None)
        if path.is_file():
            try:
                self._cp.read(path, encoding="utf-8")
            except configparser.Error as e:
                raise QBibleError(f"Cannot read configuration file {path}: {e}") from None

    def get(self, name: str) -> str:
        s = SETTINGS[name]
        if self._cp.has_option(s.section, s.key):
            try:
                return _validate(s, self._cp.get(s.section, s.key))
            except QBibleError as e:
                print(f"qbible: warning: ignoring invalid setting in {self.path}: {e}", file=sys.stderr)
        return s.default

    def get_bool(self, name: str) -> bool:
        return self.get(name) == "true"

    def get_int(self, name: str) -> int:
        return int(self.get(name))

    def set(self, name: str, value: str) -> str:
        if name not in SETTINGS:
            raise QBibleError(f"Unknown setting '{name}'. Run 'qbible config list' to see settings.")
        s = SETTINGS[name]
        v = _validate(s, value)
        if not self._cp.has_section(s.section):
            self._cp.add_section(s.section)
        self._cp.set(s.section, s.key, v)
        self._save()
        return v

    def unset(self, name: str) -> None:
        if name not in SETTINGS:
            raise QBibleError(f"Unknown setting '{name}'.")
        s = SETTINGS[name]
        if self._cp.has_option(s.section, s.key):
            self._cp.remove_option(s.section, s.key)
            self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".ini.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("# qbible configuration. See 'qbible config list'.\n")
            self._cp.write(f)
        os.replace(tmp, self.path)

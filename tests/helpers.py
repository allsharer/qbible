"""Shared test helpers.

Tests never touch real user data: :func:`isolated_env` points the user data
and configuration directories at a temporary directory.
"""

from __future__ import annotations

import io
import os
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KJV_PACK = ROOT / "build" / "translations" / "kjv.sqlite"
SPEC = ROOT / "spec"


def require_kjv(testcase: unittest.TestCase | None = None) -> Path:
    if not KJV_PACK.is_file():
        raise unittest.SkipTest(
            f"KJV pack not built ({KJV_PACK}). Run 'make data' (python3 -m qbible.build_data) first."
        )
    return KJV_PACK


class IsolatedEnv:
    """Temporary QBIBLE_DATA_HOME / QBIBLE_CONFIG_HOME for the duration of a test."""

    VARS = ("QBIBLE_DATA_HOME", "QBIBLE_CONFIG_HOME", "QBIBLE_TRANSLATIONS_PATH", "NO_COLOR",
            "QBIBLE_SHARE_DIR", "QBIBLE_WEB_DIR")

    def __enter__(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="qbible-test-"))
        self.saved = {k: os.environ.get(k) for k in self.VARS}
        for k in self.VARS:
            os.environ.pop(k, None)
        os.environ["QBIBLE_DATA_HOME"] = str(self.tmp / "data")
        os.environ["QBIBLE_CONFIG_HOME"] = str(self.tmp / "config")
        return self

    def __exit__(self, *exc):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)


def run_cli(*args: str) -> tuple[int, str, str]:
    from qbible.cli import main

    out, err = io.StringIO(), io.StringIO()
    code = main(list(args), out=out, err=err)
    return code, out.getvalue(), err.getvalue()

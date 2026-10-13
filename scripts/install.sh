#!/bin/sh
# Portable per-user installation (no root): installs into ~/.local by default.
#
#   scripts/install.sh [PREFIX]        default PREFIX: $HOME/.local
#
# Files go to PREFIX/bin/qbible and PREFIX/share/qbible (plus man page and
# bash completion). Your bookmarks and settings are never touched.
set -eu
ROOT=$(cd "$(dirname "$0")/.." && pwd)
PREFIX=${1:-$HOME/.local}
case "$PREFIX" in /*) ;; *) echo "error: PREFIX must be an absolute path" >&2; exit 2 ;; esac
if [ "$(id -u)" = 0 ] && [ -z "${1:-}" ]; then
    echo "Refusing to install into root's home. Use the .deb package for a system-wide install." >&2
    exit 2
fi
"$ROOT/scripts/stage.sh" "" "$PREFIX" "/usr/bin/env python3"
# Refresh menu and icon caches so the launcher appears straight away (best effort).
command -v update-desktop-database >/dev/null && update-desktop-database -q "$PREFIX/share/applications" || true
command -v gtk-update-icon-cache >/dev/null && [ -f "$PREFIX/share/icons/hicolor/index.theme" ] \
    && gtk-update-icon-cache -q -t "$PREFIX/share/icons/hicolor" || true
echo "Installed qbible to $PREFIX (with an app launcher: search for qbible in your applications)"
case ":$PATH:" in *":$PREFIX/bin:"*) ;; *) echo "Note: add $PREFIX/bin to your PATH." ;; esac
"$PREFIX/bin/qbible" --version

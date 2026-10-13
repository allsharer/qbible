#!/bin/sh
# Remove a per-user installation made by install.sh. User data is kept unless
# --purge is given (bookmarks, history, imported translations, settings).
set -eu
PREFIX="$HOME/.local"
PURGE=0
for a in "$@"; do
    case "$a" in
        --purge) PURGE=1 ;;
        /*) PREFIX=$a ;;
        *) echo "usage: $0 [PREFIX] [--purge]" >&2; exit 2 ;;
    esac
done
if [ ! -f "$PREFIX/share/qbible/python/qbible/__init__.py" ]; then
    echo "No qbible installation found under $PREFIX" >&2
    exit 1
fi
rm -f "$PREFIX/bin/qbible" "$PREFIX/share/man/man1/qbible.1.gz" "$PREFIX/share/bash-completion/completions/qbible"
rm -rf "$PREFIX/share/qbible" "$PREFIX/share/doc/qbible"
echo "Removed qbible from $PREFIX"
if [ "$PURGE" = 1 ]; then
    rm -rf "${QBIBLE_DATA_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/qbible}" \
           "${QBIBLE_CONFIG_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/qbible}"
    echo "Removed your qbible bookmarks, history, imported translations and settings."
else
    echo "Your bookmarks, history and settings were kept (use --purge to remove them)."
fi

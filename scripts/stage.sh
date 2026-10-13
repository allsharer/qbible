#!/bin/sh
# Copy qbible into an installation tree.
#
#   scripts/stage.sh DESTROOT PREFIX [LAUNCHER_SHEBANG]
#
# Produces DESTROOT/PREFIX/{bin/qbible, share/qbible/{python,web,translations},
# share/applications/qbible.desktop, share/icons/hicolor/*/apps/qbible.{png,svg},
# share/man/man1/qbible.1.gz, share/bash-completion/completions/qbible,
# share/doc/qbible/...}. Used by build-deb.sh and install.sh.
set -eu

DEST=${1?destination root (may be empty for a direct install)}
PREFIX=${2:?prefix, e.g. /usr}
SHEBANG=${3:-/usr/bin/python3}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
PACK="$ROOT/build/translations/kjv.sqlite"

[ -f "$PACK" ] || { echo "error: $PACK not built; run 'make data' first" >&2; exit 1; }

T="$DEST$PREFIX"
SHARE="$T/share/qbible"
umask 022
mkdir -p "$T/bin" "$SHARE/python" "$SHARE/translations" "$T/share/man/man1" \
         "$T/share/bash-completion/completions" "$T/share/doc/qbible"

# Python package (sources only, no caches) and resources.
rm -rf "$SHARE/python/qbible"
mkdir -p "$SHARE/python/qbible"
( cd "$ROOT" && find qbible -type f \( -name '*.py' -o -name '*.json' \) ! -path '*/__pycache__/*' ) |
while read -r f; do
    mkdir -p "$SHARE/python/$(dirname "$f")"
    cp "$ROOT/$f" "$SHARE/python/$f"
done
rm -f "$SHARE/python/qbible/build_data.py"   # build-time tool; needs the source tree

rm -rf "$SHARE/web"
cp -R "$ROOT/web" "$SHARE/web"
cp "$PACK" "$SHARE/translations/kjv.sqlite"
chmod 0644 "$SHARE/translations/kjv.sqlite"

sed "1s|.*|#!$SHEBANG|" "$ROOT/packaging/qbible.launcher" > "$T/bin/qbible"
chmod 0755 "$T/bin/qbible"

# Desktop entry (app drawer) and icons in the freedesktop hicolor theme.
mkdir -p "$T/share/applications" "$T/share/icons/hicolor/scalable/apps"
sed "s|@BINDIR@|$PREFIX/bin|" "$ROOT/packaging/qbible.desktop.in" > "$T/share/applications/qbible.desktop"
cp "$ROOT/packaging/icons/qbible.svg" "$T/share/icons/hicolor/scalable/apps/qbible.svg"
for png in "$ROOT"/packaging/icons/hicolor/*/apps/qbible.png; do
    size=$(basename "$(dirname "$(dirname "$png")")")
    mkdir -p "$T/share/icons/hicolor/$size/apps"
    cp "$png" "$T/share/icons/hicolor/$size/apps/qbible.png"
done

gzip -9n -c "$ROOT/packaging/qbible.1" > "$T/share/man/man1/qbible.1.gz"
( cd "$ROOT" && python3 -m qbible completion bash ) > "$T/share/bash-completion/completions/qbible"

cp "$ROOT/README.md" "$ROOT/THIRD_PARTY_NOTICES.md" "$T/share/doc/qbible/"
cp "$ROOT/build/translations/kjv-validation.txt" "$T/share/doc/qbible/kjv-validation.txt"
cp "$ROOT/data/sources/eng-kjv_about.htm" "$T/share/doc/qbible/kjv-source-about.htm"

find "$T" -type d -exec chmod 0755 {} +
find "$SHARE" "$T/share/doc/qbible" "$T/share/man" "$T/share/bash-completion" "$T/share/applications" \
     "$T/share/icons" -type f -exec chmod 0644 {} +
chmod 0755 "$T/bin/qbible"

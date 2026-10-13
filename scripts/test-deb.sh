#!/bin/sh
# Verify a built .deb without installing it system-wide (no root needed):
# metadata, file list, ownership, lintian, then run the extracted copy.
set -eu
DEB=${1:?path to .deb}
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "ok   $*"; }

dpkg-deb --info "$DEB" >/dev/null || fail "not a valid .deb"
pass "valid Debian archive"
dpkg-deb --field "$DEB" Package Version Architecture Depends

LIST=$(dpkg-deb --contents "$DEB")
for f in ./usr/bin/qbible ./usr/share/qbible/translations/kjv.sqlite ./usr/share/qbible/web/index.html \
         ./usr/share/qbible/python/qbible/cli.py ./usr/share/man/man1/qbible.1.gz \
         ./usr/share/bash-completion/completions/qbible ./usr/share/doc/qbible/copyright \
         ./usr/share/applications/qbible.desktop ./usr/share/icons/hicolor/scalable/apps/qbible.svg \
         ./usr/share/icons/hicolor/16x16/apps/qbible.png ./usr/share/icons/hicolor/48x48/apps/qbible.png \
         ./usr/share/icons/hicolor/256x256/apps/qbible.png ./usr/share/icons/hicolor/512x512/apps/qbible.png; do
    echo "$LIST" | grep -q " $f\$" || fail "missing $f"
done
pass "expected files present"
echo "$LIST" | grep -qv ' root/root ' && fail "files not owned by root" || true
echo "$LIST" | awk '{print $6}' | grep -E '^\./(home|root|etc|var|opt)/' && fail "files outside /usr" || true
echo "$LIST" | grep -q '__pycache__' && fail "__pycache__ in package" || true
echo "$LIST" | grep -q 'rwxr-xr-x root/root.*\./usr/bin/qbible' || fail "/usr/bin/qbible not executable"
pass "ownership, permissions and locations follow Debian conventions"

if command -v lintian >/dev/null; then
    lintian --tag-display-limit 0 "$DEB" > "$WORK/lintian.txt" 2>&1 || true
    if grep -q '^E:' "$WORK/lintian.txt"; then cat "$WORK/lintian.txt"; fail "lintian errors"; fi
    if [ -s "$WORK/lintian.txt" ]; then echo "lintian notes:"; sed 's/^/     /' "$WORK/lintian.txt"; fi
    pass "lintian: no errors"
fi

dpkg-deb -x "$DEB" "$WORK/root"

DESKTOP="$WORK/root/usr/share/applications/qbible.desktop"
if command -v desktop-file-validate >/dev/null; then
    desktop-file-validate "$DESKTOP" || fail "desktop entry does not validate"
fi
grep -qx 'Exec=/usr/bin/qbible serve --open --exit-when-closed' "$DESKTOP" || fail "desktop Exec line"
grep -qx 'Icon=qbible' "$DESKTOP" || fail "desktop Icon line"
for png in "$WORK"/root/usr/share/icons/hicolor/*/apps/qbible.png; do
    size=$(basename "$(dirname "$(dirname "$png")")")
    file "$png" | grep -q "PNG image data, ${size%x*} x ${size#*x}," || fail "icon $size has wrong dimensions"
done
pass "app launcher: valid desktop entry and icons ($(ls "$WORK"/root/usr/share/icons/hicolor | tr '\n' ' '))"
export QBIBLE_DATA_HOME="$WORK/data" QBIBLE_CONFIG_HOME="$WORK/config"
Q="$WORK/root/usr/bin/qbible"
"$Q" --version
"$Q" paths | grep -q "$WORK/root/usr/share/qbible/translations" || fail "extracted copy does not use its own share dir"
[ "$("$Q" read John 11:35 --no-heading)" = "35 Jesus wept." ] || fail "read"
"$Q" search "faith without works" --count | grep -qx 2 || fail "search"
"$Q" validate | grep -q "RESULT: VALID" || fail "validate"
"$Q" bookmark add Ps 23 >/dev/null 2>&1 && "$Q" bookmarks | grep -q "Psalm 23" || fail "bookmarks"
[ -f "$WORK/data/user.sqlite" ] || fail "user data not in QBIBLE_DATA_HOME"
"$Q" serve --port 0 > "$WORK/serve.log" 2>&1 &
PID=$!
for _ in 1 2 3 4 5 6 7 8 9 10; do grep -q 'running at' "$WORK/serve.log" && break; sleep 0.5; done
URL=$(sed -n 's/.*running at \(http[^ ]*\).*/\1/p' "$WORK/serve.log")
[ -n "$URL" ] || { kill -TERM $PID; cat "$WORK/serve.log"; fail "server did not start"; }
python3 - "$URL" <<'EOF' || { kill -TERM $PID; fail "server"; }
import json, sys, urllib.request
base = sys.argv[1]
assert json.load(urllib.request.urlopen(base + "api/v1/passage?ref=Gen%201:1"))["chapters"][0]["verses"][0]["text"].startswith("In the beginning")
assert b"qbible" in urllib.request.urlopen(base).read()
EOF
kill -TERM $PID; wait $PID 2>/dev/null || true  # background jobs in sh ignore SIGINT
pass "extracted package runs: read, search, validate, bookmarks, browser server"
echo "All package checks passed."

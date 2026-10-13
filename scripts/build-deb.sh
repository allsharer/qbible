#!/bin/sh
# Build dist/qbible_<version>_all.deb with dpkg-deb (no root needed).
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/qbible/__init__.py")
MAINTAINER=${QBIBLE_MAINTAINER:-"qbible maintainers <allsharer@gmail.com>"}
STAGE="$ROOT/build/deb/qbible_${VERSION}_all"
DIST=${QBIBLE_DIST_DIR:-$ROOT/dist}   # override to build somewhere else
OUT="$DIST/qbible_${VERSION}_all.deb"

command -v dpkg-deb >/dev/null || { echo "error: dpkg-deb not found (install dpkg-dev)" >&2; exit 1; }

rm -rf "$STAGE"
mkdir -p "$STAGE/DEBIAN" "$DIST"
"$ROOT/scripts/stage.sh" "$STAGE" /usr /usr/bin/python3

DOC="$STAGE/usr/share/doc/qbible"
cp "$ROOT/packaging/copyright" "$DOC/copyright"
gzip -9n "$DOC/README.md" "$DOC/THIRD_PARTY_NOTICES.md" "$DOC/kjv-validation.txt"
DATE=$(date -R -d "@${SOURCE_DATE_EPOCH:-$(stat -c %Y "$ROOT/qbible/__init__.py")}")
printf 'qbible (%s) stable; urgency=medium\n\n  * Release %s. See README.md.\n\n -- %s  %s\n' \
    "$VERSION" "$VERSION" "$MAINTAINER" "$DATE" | gzip -9n > "$DOC/changelog.gz"
chmod 0644 "$DOC"/*

SIZE=$(du -sk --exclude=DEBIAN "$STAGE" | cut -f1)
cat > "$STAGE/DEBIAN/control" <<EOF
Package: qbible
Version: $VERSION
Section: text
Priority: optional
Architecture: all
Depends: python3 (>= 3.10)
Suggests: bash-completion
Installed-Size: $SIZE
Maintainer: $MAINTAINER
Description: modern, ad-free Bible reader (King James Version)
 qbible reads, searches and navigates the complete King James Version of
 the Bible. It provides a full command-line interface (reading, reference
 navigation, word and phrase search, bookmarks, reading history and an
 interactive mode) and a local browser interface started with
 'qbible serve'. Everything works offline; there are no adverts and no
 tracking. Additional translations can be imported by the user.
EOF

( cd "$STAGE" && find usr -type f -print0 | sort -z | xargs -0 md5sum ) > "$STAGE/DEBIAN/md5sums"
chmod 0644 "$STAGE/DEBIAN/control" "$STAGE/DEBIAN/md5sums"

dpkg-deb --root-owner-group -Zxz --build "$STAGE" "$OUT" >/dev/null
echo "Built $OUT"
dpkg-deb --info "$OUT" | sed -n '1,4p;/Package:/,$p'

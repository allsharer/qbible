#!/bin/sh
# Full release build: data -> tests -> .deb -> package checks -> source tarball -> checksums.
#   scripts/release.sh            (set SKIP_BROWSER_TESTS=1 if Chrome/npm are unavailable)
set -eu
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' qbible/__init__.py)

echo "== Building KJV translation pack"
python3 -m qbible.build_data >/dev/null
echo "== Python tests"
python3 -m unittest discover -s tests -t .
if [ "${SKIP_BROWSER_TESTS:-0}" != 1 ]; then
    echo "== Browser tests"
    [ -d node_modules/puppeteer-core ] || npm install --no-audit --no-fund
    npm run --silent test:browser
else
    echo "== Browser tests SKIPPED (SKIP_BROWSER_TESTS=1)"
fi
echo "== Debian package"
scripts/build-deb.sh
scripts/test-deb.sh "dist/qbible_${VERSION}_all.deb"
echo "== Source tarball"
tar --exclude=./build --exclude=./dist --exclude=./node_modules --exclude='*/__pycache__' \
    --exclude=./.git --transform "s|^\.|qbible-$VERSION|" -czf "dist/qbible-$VERSION.tar.gz" .
( cd dist && sha256sum "qbible_${VERSION}_all.deb" "qbible-$VERSION.tar.gz" > SHA256SUMS )
echo "== Done"
cat dist/SHA256SUMS

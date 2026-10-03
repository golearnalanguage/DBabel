#!/bin/sh
# Build an Apple Silicon macOS app with a bundled Python/OpenSSL runtime.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
OUTPUT="$ROOT/output"
TOOLS="$OUTPUT/build-tools"
UV="$TOOLS/bin/uv"
PYTHONS="$OUTPUT/build-python"
PYTHON="$PYTHONS/cpython-3.12.14-macos-aarch64-none"
VENDOR="$OUTPUT/build-vendor"
RELEASE="${DBABEL_RELEASE_DIR:-$OUTPUT/release}"
APP="$RELEASE/DBabel.app"
DMG="$RELEASE/DBabel-macOS-AppleSilicon.dmg"
BUILD_TMP=$(mktemp -d "${TMPDIR:-/tmp}/dbabel-package.XXXXXX")
trap 'rm -rf "$BUILD_TMP"' EXIT
STAGE="$BUILD_TMP/dmg-stage"
DMG_TEMP="$BUILD_TMP/DBabel-macOS-AppleSilicon.dmg"

if [ ! -x "$UV" ]; then
  /usr/bin/python3 -m pip install --disable-pip-version-check \
    --target "$TOOLS" 'uv==0.12.19'
fi
if [ ! -x "$PYTHON/bin/python3" ]; then
  "$UV" python install 3.12.14 --install-dir "$PYTHONS" --no-bin
fi
"$UV" pip install --target "$VENDOR" --python "$PYTHON/bin/python3" \
  -r "$ROOT/requirements-dev.txt"

mkdir -p "$RELEASE"
rm -rf "$APP"
DBABEL_DESKTOP_APP_PATH="$APP" sh "$ROOT/scripts/build_macos_app.sh" >/dev/null
mkdir -p "$APP/Contents/Resources/DBabel" "$STAGE"
ditto "$PYTHON" "$APP/Contents/Resources/Python"
ditto "$VENDOR" "$APP/Contents/Resources/vendor"
rsync -a \
  --exclude='.git/' --exclude='.venv*/' --exclude='output/' \
  --exclude='__pycache__/' --exclude='.pytest_cache/' --exclude='tests/' \
  --exclude='cache/' --exclude='source_cache/' --exclude='private/' \
  --exclude='customer_data/' --exclude='project_glossary_private/' \
  --exclude='translation_memory_private/' --exclude='.env' \
  --exclude='.env.*' --exclude='*.key' --exclude='*.pem' \
  --exclude='*.p12' --exclude='*.pfx' --exclude='.DS_Store' \
  "$ROOT/" "$APP/Contents/Resources/DBabel/"

/usr/libexec/PlistBuddy -c 'Set :CFBundleIdentifier org.dbabel.desktop' \
  "$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c 'Add :LSMinimumSystemVersion string 13.0' \
  "$APP/Contents/Info.plist"
codesign --force --deep --sign - "$APP" >/dev/null
codesign --verify --deep --strict "$APP"

ditto "$APP" "$STAGE/DBabel.app"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname DBabel -srcfolder "$STAGE" \
  -fs HFS+ -format UDZO "$DMG_TEMP" >/dev/null
hdiutil verify "$DMG_TEMP" >/dev/null
mv -f "$DMG_TEMP" "$DMG"
printf '%s\n' "$DMG"

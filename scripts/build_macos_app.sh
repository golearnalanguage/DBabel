#!/bin/sh
# Build a local macOS app that uses this checkout and its Python environment.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
APP="${DBABEL_DESKTOP_APP_PATH:-$ROOT/output/desktop/DBabel.app}"
MACOS="$APP/Contents/MacOS"
RESOURCES="$APP/Contents/Resources"
mkdir -p "$MACOS" "$RESOURCES"

swiftc -parse-as-library -O \
  "$ROOT/desktop/macos/DesktopBackend.swift" \
  "$ROOT/desktop/macos/DBabelApp.swift" \
  -o "$MACOS/DBabel"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>DBabel</string>
  <key>CFBundleDisplayName</key><string>DBabel</string>
  <key>CFBundleIdentifier</key><string>org.dbabel.desktop.local</string>
  <key>CFBundleExecutable</key><string>DBabel</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.5.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>CFBundleIconFile</key><string>DBabelIcon</string>
  <key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST

ICON_TMP=$(mktemp -d "${TMPDIR:-/tmp}/dbabel-icon.XXXXXX")
trap 'rm -rf "$ICON_TMP"' EXIT
ICONSET="$ICON_TMP/DBabelIcon.iconset"
mkdir -p "$ICONSET"
sips -Z 900 "$ROOT/review_workbench/static/dbabel-workbench-logo.png" \
  --out "$ICON_TMP/logo-scaled.png" >/dev/null
sips -p 1024 1024 --padColor FFFFFF "$ICON_TMP/logo-scaled.png" \
  --out "$ICON_TMP/logo-square.png" >/dev/null
for size in 16 32 128 256 512; do
  sips -z "$size" "$size" "$ICON_TMP/logo-square.png" \
    --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
  double=$((size * 2))
  sips -z "$double" "$double" "$ICON_TMP/logo-square.png" \
    --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$RESOURCES/DBabelIcon.icns"

echo "$APP"

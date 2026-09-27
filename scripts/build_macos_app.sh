#!/bin/sh
# Build a local macOS app that uses this checkout and its Python environment.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
APP="${DBABEL_DESKTOP_APP_PATH:-$ROOT/output/desktop/DBabel.app}"
MACOS="$APP/Contents/MacOS"
mkdir -p "$MACOS"

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
  <key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST

echo "$APP"

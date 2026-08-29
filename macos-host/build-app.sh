#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
swift build -c debug
APP="$ROOT/.artifacts/Cauco.app"; rm -rf "$APP"; mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$ROOT/.build/debug/CaucoHost" "$APP/Contents/MacOS/Cauco"
cp "$ROOT/Resources/Info.plist" "$APP/Contents/Info.plist"
cp -R "$ROOT/Resources/WakeWord" "$APP/Contents/Resources/WakeWord"
codesign --force --deep --sign - "$APP"
echo "$APP"

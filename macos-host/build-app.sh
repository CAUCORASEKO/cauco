#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
swift build -c debug
APP="$ROOT/.artifacts/Cauco.app"; rm -rf "$APP"; mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$ROOT/.build/debug/CaucoHost" "$APP/Contents/MacOS/Cauco"
cp "$ROOT/Resources/Info.plist" "$APP/Contents/Info.plist"
cp -R "$ROOT/Resources/WakeWord" "$APP/Contents/Resources/WakeWord"

# Real signing is required for Launch at Login registration. Keep ad-hoc
# signing available only as an explicit opt-in for development builds.
identity_listing="$(security find-identity -v -p codesigning 2>/dev/null || true)"
if [ "${CAUCO_ADHOC_SIGN:-0}" = "1" ]; then
  signing_mode="ad-hoc"
  signing_identity="-"
else
  requested_identity="${CAUCO_CODESIGN_IDENTITY:-}"
  if [ -n "$requested_identity" ]; then
    if ! printf '%s\n' "$identity_listing" | grep -Fq "\"$requested_identity\"" &&
      ! printf '%s\n' "$identity_listing" | grep -Fq " $requested_identity \""; then
      echo "build-app: error: CAUCO_CODESIGN_IDENTITY is not a valid codesigning identity" >&2
      exit 1
    fi
    signing_identity="$requested_identity"
  else
    signing_identity="$(printf '%s\n' "$identity_listing" | awk '/"Apple Development:/{print $2; exit}')"
    if [ -z "$signing_identity" ]; then
      echo "build-app: error: no valid Apple Development identity found; set CAUCO_ADHOC_SIGN=1 only for non-Launch-at-Login builds" >&2
      exit 1
    fi
  fi
  signing_mode="Apple Development"
fi

echo "build-app: signing mode: $signing_mode"
codesign --force --deep --sign "$signing_identity" "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"
echo "$APP"

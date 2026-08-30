#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
BUILD_SCRIPT="$ROOT/macos-host/build-app.sh"
BUILT_APP="$ROOT/macos-host/.artifacts/Cauco.app"
INSTALL_PATH="/Applications/Cauco.app"
EXECUTABLE="$INSTALL_PATH/Contents/MacOS/Cauco"
STARTUP_TIMEOUT_SECONDS=20

die() { printf 'install-app: error: %s\n' "$*" >&2; exit 1; }

[[ -x "$BUILD_SCRIPT" ]] || die "missing executable build workflow: $BUILD_SCRIPT"
[[ -d "$ROOT/macos-host/Resources" ]] || die "missing macOS host resources"
[[ -f "$ROOT/macos-host/Resources/Info.plist" ]] || die "missing Info.plist"
command -v swift >/dev/null || die "swift is required"
command -v open >/dev/null || die "open is required"
command -v curl >/dev/null || die "curl is required"

stop_owned_hosts() {
  local pid command_line
  while read -r pid; do
    [[ -n "$pid" ]] || continue
    command_line="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    if [[ "$command_line" == "/Applications/Cauco.app/Contents/MacOS/Cauco" ||
      "$command_line" == "$INSTALL_PATH/Contents/MacOS/Cauco" ]]; then
      kill -TERM "$pid" 2>/dev/null || true
    fi
  done < <(pgrep -f '/Applications/Cauco\.app/Contents/MacOS/Cauco' || true)
  sleep 1
}

printf 'Building Cauco.app…\n'
(cd "$ROOT/macos-host" && "$BUILD_SCRIPT") >/dev/null
[[ -d "$BUILT_APP" ]] || die "build did not produce $BUILT_APP"
[[ -f "$BUILT_APP/Contents/Info.plist" ]] || die "built app is missing Info.plist"
[[ -x "$BUILT_APP/Contents/MacOS/Cauco" ]] || die "built app is missing executable"
if [[ -e "$ROOT/macos-host/Resources/WakeWord" ]]; then
  [[ -d "$BUILT_APP/Contents/Resources/WakeWord" ]] || die "built app is missing WakeWord resources"
fi

stop_owned_hosts

stage="$(mktemp -d "/Applications/.Cauco.install.XXXXXX")"
backup="/Applications/.Cauco.previous.$$"
installed=0
cleanup() {
  if [[ "$installed" -eq 0 && -d "$backup" && ! -e "$INSTALL_PATH" ]]; then
    mv "$backup" "$INSTALL_PATH" || true
  fi
  rm -rf "$stage"
}
trap cleanup EXIT

cp -R "$BUILT_APP" "$stage/Cauco.app"
if [[ -e "$INSTALL_PATH" ]]; then mv "$INSTALL_PATH" "$backup"; fi
mv "$stage/Cauco.app" "$INSTALL_PATH"
installed=1
[[ -x "$EXECUTABLE" ]] || die "installed app is missing executable"

open -n "$INSTALL_PATH"
host_pid=""
for ((attempt = 0; attempt < STARTUP_TIMEOUT_SECONDS * 2; attempt++)); do
  host_pid="$(pgrep -f '/Applications/Cauco\.app/Contents/MacOS/Cauco' | head -n 1 || true)"
  if [[ -n "$host_pid" ]] && curl -fsS -o /dev/null --max-time 1 "http://127.0.0.1:8765/health"; then break; fi
  sleep 0.5
done
[[ -n "$host_pid" ]] || die "Cauco Host did not start from /Applications"
curl -fsS -o /dev/null --max-time 2 "http://127.0.0.1:8765/health" || die "Core health check failed"

if [[ -d "$backup" ]]; then rm -rf "$backup"; fi
printf 'build succeeded\ninstalled path: %s\nHost PID: %s\nCore health: HTTP 200\n' "$INSTALL_PATH" "$host_pid"
if wake_status="$(curl -fsS --max-time 2 "http://127.0.0.1:8765/api/native/wakeword/status" 2>/dev/null)"; then
  printf 'wakeword.status: %s\n' "$wake_status"
else
  printf 'wakeword.status: unavailable (Core does not expose this endpoint)\n'
fi

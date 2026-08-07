# Cauco macOS Host v1

The host is a small native SwiftUI `.app` whose stable identity (`com.cauco.host`) owns the macOS Contacts permission. It is a development host, not the final Cauco interface and not a replacement for the Obsidian plugin.

It never requests permission or reads private data at startup. The Contacts button performs one explicit `CNContactStore.requestAccess` call; the host does not enumerate, search, display, persist, or modify contacts. Only the host's native authorization state is shown. The Python connector's ability to use that authorization is intentionally unverified and must not be assumed. If macOS continues to deny Python access, a future capability broker (XPC, authenticated localhost IPC, or a Unix socket) should expose only allowlisted, bounded operations.

Core launch is development-only: the installed `Cauco.app` does not contain the Python Core. A development user must select the local Cauco repository in the **Development Core** section. The selected directory is persisted only as a local UserDefaults repository path. Resolution order is UserDefaults, the allowlisted `CAUCO_REPOSITORY_PATH` environment variable, then a repository-relative fallback only when the executable is actually running from a repository build tree. Otherwise the Host reports **Repository path is not configured**; it never derives `/.venv/bin/python`.

The selected repository must be a non-root, non-symlinked directory containing `core/pyproject.toml` and `.venv/bin/python`. Virtualenv Python entries may legitimately be symbolic links: the Host resolves the logical path with Foundation URL APIs to validate it, rejects broken links/directories/non-executable destinations, and launches the logical repository entrypoint itself. This preserves virtualenv context and prevents a Homebrew or system destination from replacing the repository interpreter. Arbitrary executable paths remain prohibited. `agents/`, `tools/`, and `scheduler/` are expected development directories. The Host constructs paths with URL components, never searches the filesystem or PATH, and passes fixed `Process.executableURL` arguments: `-m uvicorn cauco_core.main:app --host 127.0.0.1 --port 8765`. Selecting or clearing a repository never starts Core automatically. Core remains bound to `127.0.0.1`; health is checked only at `http://127.0.0.1:8765/health` with bounded retries and sanitized diagnostics. Failed launches clear ownership and return the UI to **Start Core**; **Stop Core** appears only for an owned child. Production packaging will later bundle or install a managed runtime. No personal path is committed.

## Verified TCC boundary and broker decision

The real Mac smoke test verified that Contacts permission granted to `com.cauco.host` is not visible to a separately launched Python Core: the Host reports `granted`, while Python reports `permission_state=not_requested`. Child-process inheritance must not be claimed. Direct Python `CNContactStore` access is therefore not the production architecture; future native capabilities must be brokered by the Host.

Native Capability Broker v1 is a typed, fail-closed contract in `CaucoHostCore`. The Host creates a private owner-only Unix socket and passes its ephemeral cryptographic token only to the owned Core child. Each connection carries one bounded JSON request and response; the token is never persisted, logged, or exposed. The closed allowlist is `contacts.status`, `contacts.search`, `contacts.get`, and `contacts.list_limited`. Only `contacts.status` is implemented, returning observational authorization metadata; the other operations are recognized and return `notImplemented`. No contact records are read or transported, no permission prompt is issued, and no arguments are logged or persisted. There are no arbitrary method names, raw Objective-C objects, unrestricted shell/native execution, or generic IPC endpoints.

## Build and sign

Deployment target is macOS 13.0. The Swift package can build for Apple Silicon or Intel; use an appropriate Xcode/Swift toolchain to produce a universal binary later. From the repository root:

```sh
cd macos-host
swift test
./build-app.sh
```

`build-app.sh` creates `.artifacts/Cauco.app` and ad-hoc signs it (`codesign --sign -`). No paid Apple Developer account is required for local testing. Keep the app in a stable disposable location because changing its path or signature can cause TCC to treat it as a new identity. No signing material, app bundle, or build output belongs in git.

## Manual TCC smoke test

Copy the app to a stable test location and launch it. Verify that startup shows `notRequested` and does not display a permission dialog. Click **Request Contacts Access**, grant access in the macOS dialog, and confirm Cauco appears under System Settings → Privacy & Security → Contacts. Record only the authorization state/result. Do not search contacts until Python inheritance has been manually proven.

To revoke access, use System Settings. If a reset is necessary, execute manually and only for this identity: `tccutil reset Contacts com.cauco.host`. The host never runs this command automatically and never edits the TCC database.

The usage description is localized-ready in the app boundary; future localization should provide English, Spanish, Finnish, and Swedish strings. v1 does not request Accessibility, microphone, speech recognition, Full Disk Access, or any other capability, and has no voice, UI automation, background agent, arbitrary shell, or unrestricted IPC.

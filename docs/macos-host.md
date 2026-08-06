# Cauco macOS Host v1

The host is a small native SwiftUI `.app` whose stable identity (`com.cauco.host`) owns the macOS Contacts permission. It is a development host, not the final Cauco interface and not a replacement for the Obsidian plugin.

It never requests permission or reads private data at startup. The Contacts button performs one explicit `CNContactStore.requestAccess` call; the host does not enumerate, search, display, persist, or modify contacts. Only the host's native authorization state is shown. The Python connector's ability to use that authorization is intentionally unverified and must not be assumed. If macOS continues to deny Python access, a future capability broker (XPC, authenticated localhost IPC, or a Unix socket) should expose only allowlisted, bounded operations.

Core launch is development-only: the host uses the repository's `.venv/bin/python`, fixed `-m uvicorn cauco_core.main:app --host 127.0.0.1 --port 8765` arguments, and owns only the resulting child `Process`. It does not accept shell text, use a shell, kill unrelated processes, expose Core externally, or persist raw logs. The current UI provides start/stop and safe status scaffolding; health polling and an existing-Core connection mode are future work.

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

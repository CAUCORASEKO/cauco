# Security boundaries

The foundation release is deliberately local, read-only, and deterministic.

## Current boundaries

- Cauco Core binds to `127.0.0.1` by default and exposes only three GET endpoints.
- CORS permits a small explicit set of local Obsidian/development origins and GET requests only.
- Memory access is limited to Markdown file metadata under one configured directory.
- Paths returned by the API are relative. Symlinks resolving outside the brain root are ignored.
- File contents are not exposed by the HTTP API.
- All registered tools declare permission metadata and are currently read-only.
- The Git tool is a placeholder and does not invoke Git or a shell.
- The scheduler stores validated definitions but runs nothing.
- The Operations Agent formats structured data and does not call a model.

## Explicitly out of scope

There is no authentication, remote API, unrestricted shell access, external connector, autonomous workflow, background daemon, email sending, microphone or webcam access, wake-word listener, or LLM integration. Any future write-capable tool must have a narrow contract, explicit authorization, and an observable audit path before it is enabled.

The plugin's core URL is configurable for development, but localhost remains the safe default. Pointing it at a remote service changes the trust boundary and is not supported by this release.

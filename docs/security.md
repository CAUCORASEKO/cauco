# Security boundaries

The current release keeps data and inference local. Deterministic foundations remain separate from the opt-in local Ollama chat path.

## Current boundaries

- Cauco Core binds to `127.0.0.1` by default. Its AI routes add model discovery and one validated chat POST endpoint.
- CORS permits a small explicit set of local Obsidian/development origins and only GET and POST methods.
- Memory access is limited to Markdown file metadata under one configured directory.
- Paths returned by the API are relative. Symlinks resolving outside the brain root are ignored.
- File contents are not exposed by the HTTP API.
- All registered tools declare permission metadata and are currently read-only.
- The Git tool is a placeholder and does not invoke Git or a shell.
- The scheduler stores validated definitions but runs nothing.
- The Operations Agent formats structured data and does not call a model.
- The configured Ollama URL must use HTTP on `127.0.0.1`, `localhost`, or `::1`; requests cannot override it.
- Chat accepts only a bounded message and optional validated model name. The system prompt and generation options are controlled by core configuration.
- Chat sends the submitted message and system prompt to local Ollama. It does not automatically read memory, invoke tools, run agents, or persist history.
- Provider errors are converted to bounded messages without internal exception traces.
- Ollama local access uses no API key and no secret is stored.

## Explicitly out of scope

There is no authentication, remote/cloud AI provider, unrestricted shell access, external connector, autonomous workflow, background daemon, email sending, microphone or webcam access, wake-word listener, persistent chat history, automatic memory retrieval, model-driven tool or agent execution, or streaming. Any future write-capable tool must have a narrow contract, explicit authorization, and an observable audit path before it is enabled.

The plugin's core URL is configurable for development, but localhost remains the safe default. Pointing it at a remote service changes the trust boundary and is not supported by this release.

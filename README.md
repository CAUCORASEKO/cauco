# Cauco

> A coding agent edits files. Cauco coordinates work.

Cauco is a local-first AI work orchestration project built around Obsidian and portable Markdown memory. The current release is an intentionally deterministic foundation: it provides observable status and safe domain contracts without an AI model or autonomous execution.

## Implemented now

- A strict TypeScript Obsidian plugin with a Cauco dashboard, ribbon action, command, settings, health check, and offline states
- A local FastAPI core exposing health, system status, and bounded Markdown file metadata
- A portable Markdown brain template suitable for an Obsidian vault
- A deterministic Operations Agent and duplicate-safe agent registry
- A permission-aware tool registry with three read-only tools
- Scheduler models for inactive one-time and recurring job definitions; no scheduler process runs yet
- Automated Python tests and Ruff configuration, plus plugin type-check and production-build scripts

## Planned, not implemented

- A real LLM provider and model-backed orchestration
- Speech-to-text, text-to-speech, continuous audio, or “Hola Cauco” wake-word detection
- A background service or actual scheduled job execution
- External connectors, autonomous workflows, and animated brain/status visualization
- Authentication or remote/cloud operation

## Architecture

```text
Obsidian plugin (TypeScript)
        |
        | local read-only HTTP
        v
Cauco Core (Python/FastAPI) ---> Markdown brain directory

Independent Python contracts: agents | tools | scheduler
```

The plugin and core remain separate and communicate through the documented HTTP contract. Markdown is the portable source of truth. Current tools are read-only, the core binds to localhost by default, and no component executes arbitrary shell commands.

See [architecture](docs/architecture.md), [API contract](docs/api-contract.md), [security boundaries](docs/security.md), [development setup](docs/development.md), and the [roadmap](docs/roadmap.md).

## Quick start

Build the plugin:

```bash
cd plugin
npm install
npm run typecheck
npm run build
```

Run the local core:

```bash
cd core
python3.11 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/cauco-core
```

The default core URL is `http://127.0.0.1:8765`, and the default development brain is `brain-template/`. Detailed test commands are in [docs/development.md](docs/development.md).

## Principles

- Local-first and privacy-first
- Human-controlled autonomy
- Observable actions and explicit tool permissions
- Portable data and small modular components
- Source-level support for Apple Silicon and Intel

## License

See [LICENSE](LICENSE).

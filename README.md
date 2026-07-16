# Cauco

> A coding agent edits files. Cauco coordinates work.

Cauco is a local-first AI work orchestration project built around Obsidian and portable Markdown memory. The current release adds provider-independent local chat through Ollama while keeping memory, tools, agents, and scheduling separate from model execution.

## Implemented now

- A strict TypeScript Obsidian plugin with a Cauco dashboard, ribbon action, command, settings, health check, and offline states
- A local FastAPI core exposing health, system status, and bounded Markdown file metadata
- A local Ollama provider with availability reporting, installed-model discovery, and non-streaming chat
- Obsidian model selection and a minimal local chat interface
- A portable Markdown brain template suitable for an Obsidian vault
- A deterministic Operations Agent and duplicate-safe agent registry
- A permission-aware tool registry with three read-only tools
- Scheduler models for inactive one-time and recurring job definitions; no scheduler process runs yet
- Automated Python tests and Ruff configuration, plus plugin type-check and production-build scripts

## Planned, not implemented

- Persistent conversation history, streaming responses, and automatic memory retrieval
- Tool or agent orchestration through the model
- Speech-to-text, text-to-speech, continuous audio, or “Hola Cauco” wake-word detection
- A background service or actual scheduled job execution
- External connectors, autonomous workflows, and animated brain/status visualization
- Authentication or remote/cloud operation

## Architecture

```text
Obsidian plugin (TypeScript)
        |
        | local HTTP contract
        v
Cauco Core (Python/FastAPI) ---> Markdown brain directory (metadata only)
        |
        | provider abstraction
        v
Local Ollama API

Independent Python contracts: agents | tools | scheduler
```

The plugin and core remain separate and communicate through the documented HTTP contract. All model requests pass through the core's provider abstraction. Chat currently sends only the submitted message and Cauco's version-controlled system prompt; it does not read memory or execute tools or agents.

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

Run local Ollama separately and verify installed models:

```bash
ollama list
ollama serve
```

The default core URL is `http://127.0.0.1:8765`, Ollama URL is `http://127.0.0.1:11434`, model is `llama3.1:latest`, and development brain is `brain-template/`. The model must be installed locally; other installed Ollama models can be selected in the plugin. Detailed setup is in [docs/development.md](docs/development.md).

## Principles

- Local-first and privacy-first
- Human-controlled autonomy
- Observable actions and explicit tool permissions
- Portable data and small modular components
- Source-level support for Apple Silicon and Intel

## License

See [LICENSE](LICENSE).

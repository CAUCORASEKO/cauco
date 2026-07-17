# Cauco

> A coding agent edits files. Cauco coordinates work.

Cauco is a local-first AI work orchestration project built around Obsidian and portable Markdown memory. The current release adds controlled, read-only Markdown retrieval to provider-independent local chat through Ollama.

## Implemented now

- A strict TypeScript Obsidian plugin with a Cauco dashboard, ribbon action, command, settings, health check, and offline states
- A local FastAPI core exposing health, system status, and bounded Markdown file metadata
- A local Ollama provider with availability reporting, installed-model discovery, and non-streaming chat
- Obsidian model selection and a minimal local chat interface
- Recursive safe Markdown discovery, controlled UTF-8 reads, and deterministic text search
- Bounded memory-aware chat with visible source file names and a per-request opt-out
- A read-only Obsidian memory browser with search and safe text previews
- A portable Markdown brain template suitable for an Obsidian vault
- A deterministic Operations Agent and duplicate-safe agent registry
- A permission-aware tool registry with three read-only tools
- Scheduler models for inactive one-time and recurring job definitions; no scheduler process runs yet
- Automated Python tests and Ruff configuration, plus plugin type-check and production-build scripts

## Planned, not implemented

- Persistent conversation history and streaming responses
- Memory writing, automatic summarization, embeddings, vector storage, or semantic search
- Long-term memory extraction or agent-driven memory updates
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
Cauco Core (Python/FastAPI) ---> Markdown brain directory (read-only)
        |
        | provider abstraction
        v
Local Ollama API

Independent Python contracts: agents | tools | scheduler
```

The plugin and core remain separate and communicate through the documented HTTP contract. The core is the only authority for memory access. Relevant Markdown context is selected with deterministic text matching, size-bounded, labelled by source, and passed as untrusted reference data. Chat never writes memory or executes tools or agents.

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

Point the core at another Markdown brain without changing source code:

```bash
export CAUCO_BRAIN_DIR="/path/to/brain"
```

## Principles

- Local-first and privacy-first
- Human-controlled autonomy
- Observable actions and explicit tool permissions
- Portable data and small modular components
- Source-level support for Apple Silicon and Intel

## License

See [LICENSE](LICENSE).

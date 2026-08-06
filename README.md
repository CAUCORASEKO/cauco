# Cauco

> A coding agent edits files. Cauco coordinates work.

Cauco is a local-first AI work orchestration project built around Obsidian and portable Markdown memory. The current release includes controlled Markdown retrieval and explicitly confirmed, allowlisted memory additions.

## Implemented now

- A strict TypeScript Obsidian plugin with a Cauco dashboard, ribbon action, command, settings, health check, and offline states
- A local FastAPI core exposing health, system status, and bounded Markdown file metadata
- A minimal native macOS host for explicit Contacts permission ownership and safe local Core startup ([docs/macos-host.md](docs/macos-host.md))
- A local Ollama provider with availability reporting, installed-model discovery, and non-streaming chat
- Obsidian model selection and a minimal local chat interface
- Recursive safe Markdown discovery, controlled UTF-8 reads, and deterministic text search
- Bounded memory-aware chat with visible source file names and a per-request opt-out
- An Obsidian memory browser with read-only search/previews and reviewable memory write proposals
- Explicit **Apply Change** confirmation for memory additions; **Cancel** never changes memory
- A portable Markdown brain template suitable for an Obsidian vault
- A deterministic agent framework with inspectable Project, Git, and Research routing
- Proposal-only agents that never execute tools, Git commands, or external research
- Bounded, registry-backed agent context with visible memory provenance
- Deterministic Project, Git, and Research planning templates grounded in safe memory excerpts
- Process-local human plan review with approve, reject, cancel, TTL, and snapshot integrity
- Plan approval authorizes only the reviewed snapshot for possible future execution; it executes nothing
- A central metadata-only registry for Git, memory, filesystem, Ollama, Obsidian, calendar, and email capability contracts
- Structured plan references and readiness checks with runtime permission reported separately
- Phase 6B step-level execution for three real, allowlisted read-only operations: `git.status`, `filesystem.list_directory`, and `filesystem.read_file`
- Deny-by-default workspace containment, output/time limits, and audit records; no simulation layer or execute-all endpoint
- Phase 6C Obsidian controls for planning, review decisions, readiness, inert execution-record creation, explicit single-step execution, results, and audit events
- Plan approval, execution creation, and step execution remain visibly separate; the plugin never approves or executes automatically
- Phase 7A's first controlled local mutations: memory proposal creation/confirmation and bounded workspace text writes
- Phase 7B controlled `git.add` for an exact approved set of workspace-relative text files
- Phase 7C controlled local `git.commit` from an exact preview-bound staged tree
- Phase 7D controlled fast-forward `git.push` of exactly one approved local commit
- Every mutation requires an inert preview plus a separate operation-specific confirmation; push never stages, commits, forces, publishes tags, or continues automatically, and authentication must already be configured outside Cauco
- Scheduler models for inactive one-time and recurring job definitions; no scheduler process runs yet
- Automated Python tests and Ruff configuration, plus plugin type-check and production-build scripts

## Planned, not implemented

- Persistent conversation history and streaming responses
- Automatic summarization, embeddings, vector storage, or semantic search
- Automatic long-term memory extraction or agent-driven memory updates
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
Cauco Core (Python/FastAPI) ---> Markdown brain directory (bounded access)
        |
        | provider abstraction
        v
Local Ollama API

Independent Python contracts: agents | tools (authoritative capability catalog) | scheduler
```

The plugin and core remain separate and communicate through the documented HTTP contract. Core is the authority for memory and tool access; the plugin never reads host files, invokes Git, or spawns a process. Chat never writes memory or executes tools or agents. Approval and execution-record creation are inert. Read-only steps retain explicit step execution. Mutation steps require preview creation and a second request bound to the exact preview digest and Core-provided phrase. Only `memory.create_proposal`, `memory.confirm_proposal`, `filesystem.write_text_file`, exact-path `git.add`, and exact-tree `git.commit` are mutation-enabled. Commits use the fixed approved message and create one local commit only; they never stage or push. Push, broad staging, communication, model, Obsidian, scheduler, network, source-code, and generic filesystem mutations remain blocked. Process-local proposals, reviews, previews, locks, and execution records disappear when Core restarts.

See [architecture](docs/architecture.md), [API contract](docs/api-contract.md), [security boundaries](docs/security.md), [development setup](docs/development.md), and the [roadmap](docs/roadmap.md).

Release preparation is documented in the [release-candidate checklist](docs/release-checklist.md). The target release-candidate version is `0.1.0` for both Core and the Obsidian plugin.

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
.venv/bin/pip install -e ../agents -e ../tools -e '.[dev]'
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

# Roadmap

## Phase 1 — Foundation (implemented)

- Obsidian dashboard with connection health and status cards
- Local FastAPI core with health, status, and bounded Markdown metadata endpoints
- Portable Markdown brain template
- Deterministic Operations Agent and agent registry
- Permission-aware registry with three read-only tools
- Validated one-time and recurring scheduler job definitions

## Phase 2 — Local AI provider integration (implemented)

- Provider-independent core AI interface and service
- Local Ollama availability checks and installed-model discovery
- Configurable default or user-selected installed model
- Validated, non-streaming local chat with a version-controlled system prompt
- Obsidian model selection, provider status, and minimal chat UI
- Truthful response metadata confirming no memory, tool, or agent use

## Phase 3 — Persistent Markdown memory retrieval (implemented)

- Recursive, visible, read-only Markdown discovery under one configured root
- Safe bounded UTF-8 file reads with path and symlink containment
- Deterministic weighted lexical search with stable excerpts
- Relevant-only, source-labelled, size-bounded prompt context
- Default-on memory-aware chat with a per-request opt-out and truthful sources
- Read-only Obsidian memory count, refresh, search, list, and preview UI

## Phase 4 — Controlled local orchestration (in progress)

Implemented:

- Deterministic, process-local proposals for allowlisted memory additions
- Explicit confirmation API with atomic application, backup, and memory refresh
- Obsidian proposal review, Apply Change, Cancel, result, and recovery UI

Remaining:

- Explicit runtime composition of the existing registries
- User-approved read and narrowly scoped write tools
- Observable execution records and permission prompts
- Memory indexing and retrieval without changing Markdown as source of truth

## Phase 5 — Extended model integration

- Persistent conversation history and streaming
- Optional semantic retrieval only after explicit design and evaluation
- Automatic summarization and long-term memory extraction policies
- Tool and agent orchestration through explicit permission policies
- Evaluation fixtures, budgets, and model-independent fallbacks

## Phase 6 — Interaction and services

- Opt-in background service
- Speech-to-text and text-to-speech
- Opt-in “Hola Cauco” wake-word detection with visible microphone state
- External connectors with per-connector permissions

## Phase 7 — Advanced workflows

- User-authorized autonomous workflows
- Durable scheduling execution and recovery
- Animated brain/status visualization grounded in real observable data

Unmarked items in phases 4–7 are plans, not current capabilities. Embeddings, a vector database, semantic search, and agent-driven memory updates are not implemented.

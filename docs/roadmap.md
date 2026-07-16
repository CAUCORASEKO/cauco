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

## Phase 3 — Controlled local orchestration

- Explicit runtime composition of the existing registries
- User-approved read and narrowly scoped write tools
- Observable execution records and permission prompts
- Memory indexing and retrieval without changing Markdown as source of truth

## Phase 4 — Extended model integration

- Persistent conversation history and streaming
- Automatic memory retrieval with visible citations
- Tool and agent orchestration through explicit permission policies
- Evaluation fixtures, budgets, and model-independent fallbacks

## Phase 5 — Interaction and services

- Opt-in background service
- Speech-to-text and text-to-speech
- Opt-in “Hola Cauco” wake-word detection with visible microphone state
- External connectors with per-connector permissions

## Phase 6 — Advanced workflows

- User-authorized autonomous workflows
- Durable scheduling execution and recovery
- Animated brain/status visualization grounded in real observable data

Items in phases 3–6 are plans, not current capabilities.

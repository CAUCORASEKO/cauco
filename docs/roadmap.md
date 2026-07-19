# Roadmap

## Phase 1 — Foundation (implemented)

- Obsidian dashboard with connection health and status cards
- Local FastAPI core with health, status, and bounded Markdown metadata endpoints
- Portable Markdown brain template
- Deterministic Operations Agent and agent registry
- Permission-aware metadata registry with seven execution-disabled tool contracts
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

## Phase 5 — Extended agent and model integration (in progress)

Implemented in Phase 5A:

- Shared typed agent contract and duplicate-safe deterministic registry
- Score/priority/agent-ID routing with a minimum threshold of 40
- Proposal-only Project, Git, and Research agents
- Dedicated agent listing, detail, and routing inspection APIs
- No model-based routing, tools, or real execution

Implemented in Phase 5B:

- Registry-backed, agent-specific memory selection through the existing safe reader
- Bounded deterministic Markdown excerpts with visible provenance and limitations
- Immutable agent context, plan, and plan-step contracts
- Template-based Project, Git, and Research plans with explicit unknowns
- Dedicated planning APIs with context opt-out and no execution

Implemented in Phase 5C:

- Immutable process-local plan review records with opaque IDs and bounded TTL
- Pending, approved, rejected, cancelled, and expired lifecycle states
- Human inspection, listing, approval, rejection, and cancellation APIs
- Canonical snapshot digests and lock-protected single terminal transitions
- Explicit approval semantics that authorize a snapshot but execute nothing

Implemented in Phase 6A:

- Immutable tool, operation, permission, and validation contracts
- Thread-safe authoritative registry with seven deterministic built-ins
- Structured agent plan references and registry-backed readiness reporting
- Tool catalog, category, operation, and validation inspection APIs
- Execution disabled globally; no tool execution endpoint or executable tool implementation

Remaining:

- Persistent conversation history and streaming
- Optional semantic retrieval only after explicit design and evaluation
- Automatic summarization and long-term memory extraction policies
- Tool and agent orchestration through explicit permission policies
- Evaluation fixtures, budgets, and model-independent fallbacks
- Phase 6 execution must accept only approved, non-expired, integrity-valid snapshots and must add separate confirmation for each step/tool; it is not implemented
- Phase 6B Safe Execution Engine with explicit per-operation permission and confirmation enforcement

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

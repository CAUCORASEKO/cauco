# Architecture

Cauco consists of an Obsidian UI, a local core, a provider-isolated AI adapter, and independent Python domain packages.

```text
Obsidian plugin (TypeScript)
        |
        | local HTTP: status, models, chat
        v
Cauco Core (FastAPI) ------> configured Markdown brain (metadata only)
        |
        | AIProvider -> AIService
        v
OllamaProvider ------------> local Ollama API

Python domain foundations (no runtime loop)
  |-- agent contract + Operations Agent registry
  |-- permission-aware tool registry
  `-- scheduler job-definition registry
```

The plugin and core deliberately do not share executable code. Their boundary is the documented JSON contract in [api-contract.md](api-contract.md), with defensive validation on both sides.

## Component responsibilities

- `plugin/` renders observable state, stores the core URL and selected model, and provides non-streaming chat with explicit offline states.
- `core/` owns HTTP transport, configuration, safe memory discovery, status responses, and AI request validation.
- `core/src/cauco_core/ai/` is the only layer that knows Ollama's HTTP contract. Other code depends on the `AIProvider` interface and `AIService`.
- `brain-template/` is portable user-owned Markdown suitable for copying into an Obsidian vault.
- `agents/`, `tools/`, and `scheduler/` define small contracts and registries. They do not run autonomous loops.
- `installer/` remains reserved for a later packaging milestone.

The source uses no architecture-specific binaries, so Apple Silicon and Intel are supported at source level.

## Current AI request flow

1. The plugin submits a message and optional installed model name to Cauco Core.
2. The API validates message length and model syntax. It never accepts a provider URL or system prompt from the request.
3. `AIService` adds Cauco's version-controlled system prompt and calls the configured provider.
4. `OllamaProvider` performs a non-streaming local request and validates the response.
5. The API explicitly reports that no memory, tools, or agents were used.

Conversation history, memory retrieval, tool execution, agent orchestration, and streaming are not part of this flow.

# Architecture

Cauco consists of an Obsidian UI, a local core, a bounded memory layer, a provider-isolated AI adapter, and independent Python domain packages.

```text
Obsidian plugin (TypeScript)
        |
        | local HTTP: status, models, chat
        v
Cauco Core (FastAPI) ------> configured Markdown brain
        |                         |
        |                         `-> discovery -> reading -> search -> context
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

- `plugin/` renders observable state, stores the core URL and selected model, provides non-streaming chat, and browses memory only through the core API.
- `core/` owns HTTP transport, configuration, safe memory access, status responses, and AI request validation.
- `core/src/cauco_core/memory/` discovers visible Markdown, enforces root and size boundaries, performs deterministic lexical search, and builds bounded source-labelled context independently from the provider.
- `core/src/cauco_core/memory_writing/` creates process-local proposals and applies only explicitly confirmed, allowlisted insertions beneath existing headings using a rotating backup and atomic replacement.
- `core/src/cauco_core/ai/` is the only layer that knows Ollama's HTTP contract. Other code depends on the `AIProvider` interface and `AIService`.
- `brain-template/` is portable user-owned Markdown suitable for copying into an Obsidian vault.
- `agents/`, `tools/`, and `scheduler/` define small contracts and registries. They do not run autonomous loops.
- `installer/` remains reserved for a later packaging milestone.

The source uses no architecture-specific binaries, so Apple Silicon and Intel are supported at source level.

## Current AI request flow

1. The plugin submits a message, optional installed model name, and `use_memory` choice.
2. The API validates the request. It never accepts a provider URL or system prompt.
3. When enabled, the independent context builder searches the message, selects only top relevant files, and enforces file/count/total-character limits.
4. `AIService` keeps policy in the system prompt and places delimited, source-labelled memory in the user message as untrusted reference data.
5. `OllamaProvider` performs a non-streaming local request and validates the response.
6. The API reports the exact memory source paths used and confirms that no tools or agents ran.

Conversation history, semantic search, memory writes, tool execution, agent orchestration, and streaming are not part of the chat flow. Memory writing is a separate proposal-and-confirmation API and is never initiated by the model.

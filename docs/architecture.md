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
  |-- deterministic agent contract, registry, router, and proposal-only built-ins
  |-- permission-aware tool registry
  `-- scheduler job-definition registry
```

The plugin and core deliberately do not share executable code. Their boundary is the documented JSON contract in [api-contract.md](api-contract.md), with defensive validation on both sides.

## Component responsibilities

- `plugin/` renders observable state, stores the core URL and selected model, provides non-streaming chat, browses memory through the core API, and exposes the explicit proposal review/confirmation flow for allowlisted memory additions.
- `core/` owns HTTP transport, configuration, safe memory access, status responses, and AI request validation.
- `core/src/cauco_core/memory/` discovers visible Markdown, enforces root and size boundaries, performs deterministic lexical search, and builds bounded source-labelled context independently from the provider.
- `core/src/cauco_core/memory_writing/` creates process-local proposals and applies only explicitly confirmed, allowlisted insertions beneath existing headings using a rotating backup and atomic replacement.
- `core/src/cauco_core/ai/` is the only layer that knows Ollama's HTTP contract. Other code depends on the `AIProvider` interface and `AIService`.
- `brain-template/` is portable user-owned Markdown suitable for copying into an Obsidian vault.
- `agents/` is the canonical shared agent framework. Core injects its explicit registry and deterministic router into application state; Project, Git, and Research agents return proposals only and never invoke tools or models.
- `core/src/cauco_core/agents/` resolves only registered Memory Engine objects through the existing safe reader, bounds deterministic excerpts, and passes immutable context to the shared planning contracts.
- `core/src/cauco_core/agents/review_store.py` owns the independent, process-local plan review lifecycle, integrity checks, expiration, capacity, and lock-protected human decisions. It never executes a plan.
- `tools/` and `scheduler/` define small contracts and registries. They do not run autonomous loops.
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

## Deterministic agent routing

Agent routing is separate from chat and Ollama. Every registered routing agent evaluates the same normalized, untrusted instruction using explicit signals. Matches at or above the score threshold of 40 are ranked by score, then configured priority, then lexicographical agent ID. A relevant preferred agent may be selected, but an unrelated preference cannot bypass the threshold. Phase 5A results only describe proposed actions; they perform no repository inspection, Git operation, web request, tool call, or memory write.

Phase 5B planning remains separate from chat and follows `route → context resolver → safe Memory Engine read → bounded context → deterministic template plan`. Core selects memory by agent, kind, layer, filename classification, and explicit lexical relevance. The shared agents package receives immutable excerpts and provenance, never filesystem paths supplied by a client. Plans cite source memory IDs, expose unknowns as open questions, and remain proposal-only. Git planning does not inspect a repository, and Research planning does not retrieve external sources.

Markdown excerpt ranking prefers a project heading discovered from registered project memory, then instruction-matching headings, known agent-specific operational headings, lexical section matches, and finally the document beginning. Multiple non-overlapping sections are combined within the request cap while retaining their headings. Fallback-only context is marked as potentially insufficient.

## Human plan review

Phase 5C extends the deterministic flow to `routing → safe context → planning → review store → human decision`. Core stores the exact routing, provenance-bearing context, and plan snapshot as `pending_review`. A human may approve, reject, or cancel it before its TTL expires; lazy expiration is the fourth terminal transition. Every terminal transition is atomic under the store lock and validates the snapshot digest first.

Approval means only that the human authorized the reviewed snapshot for possible use by a future execution system. It does not invoke a tool, run a step, refresh memory, regenerate the plan, or mark work complete. Execution remains outside the current architecture, and the controlled memory-write confirmation workflow remains separate.

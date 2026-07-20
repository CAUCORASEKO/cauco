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

- `plugin/` renders observable state, stores the core URL and selected model, provides non-streaming chat, browses memory through the core API, exposes the explicit proposal review/confirmation flow for allowlisted memory additions, and acts as the human control surface for planning, plan review, readiness, and single-step read-only execution. It never executes a tool directly.
- `core/` owns HTTP transport, configuration, safe memory access, status responses, and AI request validation.
- `core/src/cauco_core/memory/` discovers visible Markdown, enforces root and size boundaries, performs deterministic lexical search, and builds bounded source-labelled context independently from the provider.
- `core/src/cauco_core/memory_writing/` creates process-local proposals and applies only explicitly confirmed, allowlisted insertions beneath existing headings using a rotating backup and atomic replacement.
- `core/src/cauco_core/ai/` is the only layer that knows Ollama's HTTP contract. Other code depends on the `AIProvider` interface and `AIService`.
- `brain-template/` is portable user-owned Markdown suitable for copying into an Obsidian vault.
- `agents/` is the canonical shared agent framework. Core injects its explicit registry and deterministic router into application state; Project, Git, and Research agents return proposals only and never invoke tools or models.
- `core/src/cauco_core/agents/` resolves only registered Memory Engine objects through the existing safe reader, bounds deterministic excerpts, and passes immutable context to the shared planning contracts.
- `core/src/cauco_core/agents/review_store.py` owns the independent, process-local plan review lifecycle, integrity checks, expiration, capacity, and lock-protected human decisions. It never executes a plan.
- `tools/` is the authoritative, thread-safe catalog of immutable tool, operation, and permission contracts. Runtime adapters are separate and exist only for three allowlisted read-only operations. `scheduler/` remains an inactive definition registry.
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

Approval means only that the human authorized the reviewed snapshot for possible execution-record creation. It does not invoke a tool, run a step, refresh memory, regenerate the plan, or mark work complete. Execution-record creation is independently inert, and the controlled memory-write confirmation workflow remains separate.

## Tool registry and readiness

Phase 6A extends the boundary to `approved plan → tool registry → validated execution contracts → stop`. Agent plan steps contain a structured `tool_id`, `operation_id`, and optional inert target. Core checks those references against the injected registry and reports whether every tool and operation is registered and enabled. This readiness result is inspection metadata, not execution readiness in the operational sense: its own `execution_enabled` flag is always false.

The registry deterministically exposes Git, memory, filesystem, Ollama, Obsidian, calendar, and email definitions. Each operation declares safety, confirmation, enablement, and runtime-policy status; each tool declares its required permissions. Disabled destructive operations remain visible for inspection but are not valid execution capabilities.

## Safe execution engine

Phase 6B implements `approved snapshot → execution record → explicit step request → registry and adapter validation → bounded read-only adapter → stored result and audit event`. Metadata definitions remain separate from runtime adapters. Only `git.status`, `filesystem.list_directory`, and `filesystem.read_file` have both runtime policy permission and an adapter.

Core owns the configured workspace root, canonical path policy, review/digest integration, execution lifecycle, in-memory record store, and audit trail. The tools package owns immutable execution contracts and fixed adapters without depending on Core. Execution creation is inert; there is no execute-all path. A step-level POST is the explicit tool confirmation for these initial read-only operations.

Execution records transition from `pending_execution` to `running`, then `completed` or `failed`; only pending records can be cancelled. Unsupported plan steps are retained as `skipped`. Store locks prevent concurrent duplicate execution of a step. Phase 5C review records and snapshot digests are never mutated.

## Controlled mutation path

Phase 7A/7B use a path separate from read-only execution: `approved immutable step → inert execution record → mutation preview → exact digest and phrase confirmation → fixed adapter → backup/post-write verification → result and audit`. Preview creation is inert. The confirmation body cannot replace the stored tool, operation, target, paths, repository, proposal ID, or content, and each preview can be claimed once.

Core owns preview lifecycle, approved-step binding, stale-state checks, audit, and the memory bridge. That bridge calls the existing Phase 4 proposal builder/store/applier rather than duplicating Markdown logic. The tools package owns the Core-independent bounded UTF-8 workspace adapter. It validates a narrow extension allowlist, writes and fsyncs a same-directory temporary, rotates up to three internal backups on replacement, atomically installs the file, and verifies the final digest. Read-only execution continues through its existing endpoint; mutations are rejected there.

Phase 7B adds a dedicated Core-independent Git staging contract and adapter. Core binds the configured repository, approved paths, before-index digest, staged-state digest, and per-path worktree state into the preview. The adapter accepts no raw argv, flags, cwd, environment, or repository input; it invokes only `git add -- <paths>`, backs up the index outside the worktree, and verifies that only approved paths became newly staged. It initially supports straightforward modified tracked and new untracked UTF-8 text files only.

## Obsidian execution control

Phase 6C/7A presents the Core lifecycle as `instruction → generated plan and provenance → review decision → readiness → inert execution record → explicit read or preview/confirmation → real result → audit trail`. The plugin keeps transient UI state separate from Core records, defensively validates essential response shapes, ignores stale manual GET responses, and never polls.

Approval, execution-record creation, and step execution are separate controls. Before a step call, the plugin refreshes authoritative readiness and requires a second click attached to that exact step. It sends only bounded timeout and output controls. Results and workspace file content are rendered as inert text through Obsidian element APIs and are not persisted into settings or the vault.

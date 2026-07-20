# HTTP API contract

The Obsidian plugin communicates with Cauco Core over local HTTP. Status, discovery, and chat do not mutate memory. A separate confirmation-only API can apply one previously stored, allowlisted memory proposal. The contract is versioned with the project at `0.1.0`.

Default base URL: `http://127.0.0.1:8765`

## `GET /health`

Returns service liveness.

```json
{
  "status": "ok",
  "service": "cauco-core",
  "version": "0.1.0"
}
```

## `GET /api/status`

Returns deterministic observable state. Counts reflect the current local configuration; no background work is implied.

```json
{
  "runtime": { "status": "online", "version": "0.1.0" },
  "memory": { "status": "ready", "files": 9 },
  "agents": { "status": "idle", "registered": 3, "active": 0 },
  "tools": { "status": "ready", "registered": 7 },
  "scheduler": { "status": "idle", "jobs": 0 }
}
```

## `GET /api/memory/files`

Lists visible, safe Markdown metadata inside the configured brain directory in deterministic path order. Hidden directories/files, non-Markdown files, unreadable files, and escaping symlinks are excluded.

```json
{
  "files": [
    {
      "relative_path": "projects/README.md",
      "name": "README.md",
      "size": 210,
      "modified_at": "2026-07-16T08:00:00Z",
      "title": "Project Notes"
    }
  ],
  "count": 1
}
```

Paths use `/` separators and are relative to the configured brain root.

## `GET /api/memory/file?path=projects.md`

Returns one safe UTF-8 Markdown file with the same metadata fields plus `content`. Only visible relative Markdown paths are accepted. Missing files return `404`, traversal or invalid paths return `400`, oversized files return `413`, and unreadable UTF-8 returns `422`.

## `GET /api/memory/search?q=project&limit=5`

Performs deterministic case-insensitive lexical matching. Title matches have weight 10, Markdown heading matches weight 5, and body matches weight 1. Results use stable score/path ordering. This is not semantic or vector search.

```json
{
  "query": "project",
  "results": [
    {
      "relative_path": "projects.md",
      "title": "Projects",
      "score": 16,
      "matched_terms": ["project"],
      "excerpt": "# Projects Current project status..."
    }
  ],
  "count": 1
}
```

`q` must contain 1–200 characters of searchable text. `limit` must be between 1 and 20.

## Memory write proposals

`POST /api/memory/write-proposals` deterministically generates and stores a review-only
proposal. Supported operations and targets are `add_task` → `Tasks.md`, `add_decision` →
`Decisions.md`, `add_relationship_note` → `Relationships.md`, and `add_project_note` →
`Projects.md`. Proposal generation does not write or refresh memory.

`GET /api/memory/write-proposals/{proposal_id}` returns the stored proposal and its
`pending`, `applied`, or `expired` state. Proposals are process-local, expire after 30
minutes by default, and do not survive a backend restart.

`POST /api/memory/write-proposals/{proposal_id}/confirm` accepts only `{"confirm": true}`.
It verifies the server-stored proposal, target allowlist, registry object, safe path, and
existing approved heading. A successful confirmation inserts the preview atomically,
rotates one `<filename>.bak` backup inside the brain root, marks the proposal applied, and
refreshes the Memory Engine. Confirmation never accepts a target path or Markdown from
the client. Duplicate content, missing sections, expired proposals, and repeated
confirmation fail without another write.

`GET /api/memory/write-operations` lists the four supported operations and targets.

## Deterministic agents

`GET /api/agents` lists immutable metadata for the registered Project, Git, and Research agents. `GET /api/agents/{agent_id}` returns one agent or `404` for an unknown ID.

`POST /api/agents/route` accepts a bounded instruction plus optional intent, scalar context, preferred agent ID, and `allow_execution`. Routing uses fixed local signals and a threshold of 40. Matches are ranked by highest score, highest configured priority, then lexicographical agent ID. A preferred agent is used only when its own match reaches the threshold.

The response includes the normalized request, all match reasoning, selected agent, and a proposal-only result. `allow_execution: true` is retained for inspection but ignored with a warning. `execution_performed` is always `false`. Phase 5A never invokes Git, a shell, tools, memory writes, Ollama, or external research. Empty normalized instructions return `400`, unknown preferred agents return `404`, and structurally invalid bodies return `422`.

### Agent context and planning

`POST /api/agents/plan` preserves Phase 5A routing and, when an agent matches, returns bounded registered-memory context plus a deterministic template plan. `POST /api/agents/{agent_id}/plan` provides explicit inspection but returns `400` if that agent does not meet the unchanged routing threshold; unknown agents return `404`.

Planning requests accept `instruction`, optional `intent` and `preferred_agent_id`, `include_context` (default `true`), `max_context_items` (default 4, maximum 8), `max_excerpt_chars` (default 2,000; range 100–4,000), and non-operative `allow_execution`. No path or memory ID input is accepted. Total returned excerpt text is independently capped at 7,000 characters.

Context contains relative memory provenance, deterministic selection reasons, truncation status, limitations, and the exact excerpts used. With `include_context: false`, no memory read occurs and the plan uses the instruction only. Plan steps cite source memory IDs and always report `execution_available: false`; the overall plan always reports `execution_performed: false`. Markdown instructions remain inert data. Git plans explicitly report that repository state is unknown, while Research plans report that no external sources were accessed. Neither routing nor planning calls Ollama.

Each memory reference also exposes `excerpt_strategy` and `selected_headings`. Strategies distinguish exact project headings, instruction-keyword headings, known operational sections, lexical sections, recent-decision fallback, and document-start fallback. `excerpt_truncated` is `true` only when the selected section text was cut by the character cap; selecting part of a document does not by itself count as truncation. Project names are derived from registered `Projects.md` headings rather than a client-provided or hard-coded target list.

### Agent plan reviews

`POST /api/agents/plan-reviews` runs the existing deterministic planning flow once and stores its exact routing, context, provenance, and plan snapshot. The request accepts the planning fields above plus optional `ttl_seconds` from 60 through 86,400; the default is 1,800 seconds. A matched plan returns `201` in `pending_review`. No match returns `409`, unknown preferred agents return `404`, and invalid bodies return `422`.

```json
{
  "instruction": "What should I work on next in Cauco?",
  "max_context_items": 4,
  "max_excerpt_chars": 1200,
  "ttl_seconds": 1800
}
```

Each record includes `review_id`, lifecycle timestamps, `instruction`, `selected_agent_id`, the stored `routing`, `context`, and `plan`, `snapshot_digest`, review notes/reasons, and the two execution flags. IDs are opaque URL-safe `planrev_...` values. Pending, rejected, cancelled, and expired records have `execution_authorized: false`; approved records have `execution_authorized: true`. `execution_performed` is always `false`.

`GET /api/agents/plan-reviews/{review_id}` returns the exact stored snapshot and its current lifecycle state. Lazy expiration is visible as `expired` with `expired_at`; retrieval still returns `200`. Unknown IDs return `404`.

`GET /api/agents/plan-reviews` lists newest first, with stable review-ID tie-breaking. It accepts optional `status`, `agent_id`, and `limit` filters. The default limit is 20 and maximum is 100.

Human decisions use these endpoints:

- `POST /api/agents/plan-reviews/{review_id}/approve` accepts optional `reviewer_note`.
- `POST /api/agents/plan-reviews/{review_id}/reject` requires `reason` and accepts optional `reviewer_note`.
- `POST /api/agents/plan-reviews/{review_id}/cancel` accepts optional `reason` and `reviewer_note`.

Reviewer notes are capped at 2,000 characters and reasons at 1,000. They are inert text. Line endings and outer whitespace are normalized; their content is never routed or executed. Invalid or repeated terminal transitions, including actions on expired records, return `409`. Unknown transition targets return `404` and invalid input returns `422`.

The SHA-256 `snapshot_digest` covers canonical JSON for the instruction, selected agent, full routing decision, context provenance and excerpts, plan steps and metadata, and the non-execution flags at review creation. Lifecycle timestamps, status, notes, and reasons are excluded, so the digest stays unchanged after a valid human decision. Every transition verifies integrity and fails with `409` if the stored snapshot differs.

Records are in-memory only and disappear when Core restarts. The store retains at most 100 records by default. At capacity it lazily expires pending records and may evict the oldest terminal records, but it never silently evicts a still-valid pending record; creation returns `409` if all capacity is active. Approval returns the warning `Approval authorizes the reviewed plan snapshot only. No action was executed.` There is no execution endpoint.

Plan and plan-review responses include structured `tool_reference` data on every step and a registry-derived `readiness` object. `ready` means every referenced tool and operation currently exists and is enabled. It does not mean actions can run: readiness and every reference report `execution_enabled: false`.

## Tool registry inspection

`GET /api/tools` returns all tool definitions in deterministic ID order. `GET /api/tools/{tool_id}` returns one definition, `GET /api/tools/categories` returns stable categories, and `GET /api/tools/{tool_id}/operations` returns stable operation contracts. Unknown tools return `404`.

`POST /api/tools/validate` accepts `{"tool_id":"git","operation_id":"status"}` and reports registration, tool/operation enablement, safety, confirmation requirements, and `execution_enabled: false`. Unknown or disabled references return `valid: false`; validation never invokes the operation.

The built-in catalog contains `git`, `memory`, `filesystem`, `ollama`, `obsidian`, `calendar`, and `email`. Runtime policy allows the three read-only operations and preview-first mutations including exact-path `git.add`. Catalog responses expose `runtime_execution_allowed`; readiness additionally exposes adapter availability and `executable_now`.

## Step-level execution

`POST /api/executions` with `{"review_id":"planrev_..."}` creates an inert `pending_execution` record and returns `201`. The review must be approved, unexpired, execution-authorized, and integrity-valid. One record is allowed per review. Creation never invokes an adapter.

`POST /api/executions/{execution_id}/steps/{step_index}/execute` executes exactly the stored operation from that approved step. The body accepts only bounded controls: `timeout_seconds` (0.1–30), `max_output_chars` (100–100,000), `max_chars` (1–100,000), and `max_entries` (1–1,000). It cannot replace the tool, operation, target, cwd, Git arguments, or command. For the three read-only operations, this POST is the explicit tool-level confirmation.

`GET /api/executions/{execution_id}` retrieves a record. `GET /api/executions` lists newest first with optional `status`, `review_id`, and `limit` filters. `POST /api/executions/{execution_id}/cancel` cancels only a pending record. There is no execute-all or arbitrary-tool endpoint.

Execution states are `pending_execution`, `running`, `completed`, `failed`, and `cancelled`. Step states are `pending`, `running`, `completed`, `failed`, `skipped`, and `cancelled`. A review record always retains `execution_performed: false`; an execution and step record become true only after a real adapter invocation. Validation rejection remains false. Timeout produces a stored failed step with a safe error and audit event.

Unknown reviews/executions/steps return `404`; ineligible reviews, digest failures, repeated creation/execution, and runtime-disabled operations return `409`; invalid controls return `422`; forbidden or sensitive paths return `403`. Responses contain workspace-relative paths only. Execution records and audit events are process-local and disappear on restart.

### Mutation preview and confirmation

- `POST /api/executions/{execution_id}/steps/{step_index}/mutation-preview` creates an inert immutable preview (`201`).
- `GET /api/executions/{execution_id}/steps/{step_index}/mutation-preview` returns the active preview.
- `POST /api/executions/{execution_id}/steps/{step_index}/confirm-mutation` claims and executes it once (`200`).
- `POST /api/executions/{execution_id}/steps/{step_index}/cancel-mutation-preview` cancels a pending preview.

The preview includes the exact stored operation, relative target, normalized approved arguments, safe before/after metadata, bounded textual diff, SHA-256 `preview_digest`, expiry, and operation-specific `confirmation_phrase`. Its digest covers the full normalized mutation even when display output is bounded. Confirmation accepts only `preview_id`, `preview_digest`, and `confirmation_phrase`; generic confirmation such as `yes` is invalid. Digest mismatch, stale state, expired/cancelled/consumed previews, invalid review state, and duplicate confirmation return conflicts. Phrase mismatch and invalid text return `422`; forbidden targets return `403`.

For `git.add`, the approved input is only `paths`. Preview output uses relative paths and a safe repository label and binds the current index, staged state, and approved worktree state. Confirmation requires `STAGE APPROVED FILES`; the client cannot send paths or Git options. The implementation rejects broad/pathspec staging, partial staging, deleted targets, ignored or sensitive paths, non-regular or binary files, oversized sets, and active merge/rebase-style states.

Preview creation leaves `execution_performed=false`. Adapter invocation sets it true even if the adapter safely fails. `mutation_performed=true` only reports a verified persistent-state change; duplicate-prevented memory content can be execution-performed without being mutation-performed.

### Obsidian client behavior

The Phase 6C plugin calls planning and review endpoints separately, retrieves readiness from planning/review responses, creates an execution record only after an explicit click, and calls a single stored step endpoint only after an inline two-click confirmation. Approval never chains into execution creation, and execution creation never chains into step execution.

The plugin read-only step request sends only `timeout_seconds` and `max_output_chars`. A mutation confirmation sends only the three integrity/interaction fields above; it never sends content or a target. GET refreshes are manual and stale responses are ignored; there is no polling. POST actions are never automatically retried.

## `GET /api/ai/status`

Reports provider availability and whether the configured default model appears in Ollama's installed model list. An unavailable Ollama service returns `200` with `available: false` so the dashboard can present an offline state.

```json
{
  "provider": "ollama",
  "available": true,
  "base_url": "http://127.0.0.1:11434",
  "default_model": "llama3.1:latest",
  "default_model_installed": true,
  "models_count": 2
}
```

## `GET /api/ai/models`

Returns only models reported by local Ollama. Model details may be `null` when Ollama omits them.

```json
{
  "provider": "ollama",
  "models": [
    {
      "name": "llama3.1:latest",
      "size": 4920753328,
      "parameter_size": "8.0B",
      "quantization_level": "Q4_K_M"
    }
  ]
}
```

## `POST /api/ai/chat`

Request:

```json
{
  "message": "What is Cauco?",
  "model": "llama3.1:latest",
  "use_memory": true
}
```

`model` is optional and defaults to core configuration. `use_memory` defaults to `true`. Messages are trimmed, must contain 1–8000 characters, and model names use a bounded Ollama-compatible syntax. Unknown request fields are rejected. The request cannot override the provider URL, generation options, or system prompt.

Response:

```json
{
  "provider": "ollama",
  "model": "llama3.1:latest",
  "response": "Cauco coordinates work locally.",
  "used_memory": true,
  "memory_sources": ["projects.md"],
  "used_tools": [],
  "used_agents": []
}
```

When memory is disabled or no relevant file matches, `used_memory` is `false` and `memory_sources` is empty. The source list contains only files actually placed in the bounded prompt context. `used_tools` and `used_agents` remain empty. Provider failures are sanitized: missing model `404`, malformed provider response `502`, unavailable provider `503`, and timeout `504`. Validation failures return `422`.

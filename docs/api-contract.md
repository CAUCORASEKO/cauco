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
  "agents": { "status": "idle", "registered": 1, "active": 0 },
  "tools": { "status": "ready", "registered": 3 },
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

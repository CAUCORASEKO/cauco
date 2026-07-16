# HTTP API contract

The Obsidian plugin communicates with Cauco Core over local HTTP. Status and discovery endpoints are read-only; chat performs local inference but does not mutate Cauco data. The contract is versioned with the project at `0.1.0`.

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

Lists Markdown metadata inside the configured brain directory. It never returns file contents.

```json
{
  "files": [
    { "path": "projects/README.md", "name": "README.md", "size": 210 }
  ],
  "count": 1
}
```

Paths use `/` separators and are relative to the configured brain root. Symlinks resolving outside that root and non-Markdown files are excluded. Errors use FastAPI's JSON `detail` response and an appropriate HTTP status.

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
  "model": "llama3.1:latest"
}
```

`model` is optional and defaults to core configuration. Messages are trimmed, must contain 1–8000 characters, and model names use a bounded Ollama-compatible syntax. Unknown request fields are rejected. The request cannot override the provider URL, generation options, or system prompt.

Response:

```json
{
  "provider": "ollama",
  "model": "llama3.1:latest",
  "response": "Cauco coordinates work locally.",
  "used_memory": false,
  "used_tools": [],
  "used_agents": []
}
```

The execution metadata is intentionally fixed because this phase does not retrieve memory or run tools or agents. Provider failures are sanitized: missing model `404`, malformed provider response `502`, unavailable provider `503`, and timeout `504`. Validation failures return `422`.

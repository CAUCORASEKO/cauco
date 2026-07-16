# HTTP API contract

The Obsidian plugin communicates with Cauco Core over local HTTP. The current contract is read-only and versioned with the project at `0.1.0`.

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

# Cauco Core

Cauco Core is a local HTTP service that exposes deterministic runtime and
Markdown-memory status plus provider-independent local chat through Ollama.

## Development

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/ruff check src tests
.venv/bin/cauco-core
```

The service binds to `127.0.0.1:8765`. Set `CAUCO_BRAIN_DIR` to use another
Markdown brain directory. Ollama defaults to `http://127.0.0.1:11434` with model
`llama3.1:latest`; see `docs/development.md` for supported environment overrides.

Chat does not retrieve memory or execute tools or agents.

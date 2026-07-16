# Cauco Core

Cauco Core is a small local HTTP service that exposes deterministic runtime and
Markdown-memory status to the Obsidian plugin. It does not use an AI model.

## Development

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/ruff check src tests
.venv/bin/cauco-core
```

The service binds to `127.0.0.1:8765`. Set `CAUCO_BRAIN_DIR` to use another
Markdown brain directory.

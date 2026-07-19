# Cauco Core

Cauco Core is a local HTTP service that exposes deterministic runtime status,
bounded Markdown memory, and provider-independent local chat through Ollama.

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

Chat retrieves only relevant, bounded Markdown context when requested and never writes
memory. The separate memory-writing API supports four allowlisted insertion operations.
It first generates an in-memory proposal, then requires a second request with explicit
confirmation before applying it. Proposals expire after 30 minutes by default and are
lost when Core restarts. Confirmed writes use an atomic same-directory replacement and
maintain one rotating `<filename>.bak` backup containing the previous file. Chat does not
execute tools or agents.
The Core also exposes the Phase 6A tool registry for contract inspection and plan-reference
readiness. All tool operations remain execution-disabled; there is no execution endpoint.

Regenerating an existing pending proposal returns its originally stored payload without
extending its expiry. Regenerating an applied proposal does not make it pending again;
an expired proposal may be generated again as a fresh pending record.

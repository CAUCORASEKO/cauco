# Development

## Requirements

- Node.js 20 or newer and npm
- Python 3.11 or newer
- Obsidian desktop for manual plugin testing
- Ollama for local model discovery and chat

All source code is architecture-neutral and supports Apple Silicon and Intel systems.

## Obsidian plugin

```bash
cd plugin
npm install
npm run typecheck
npm run build
```

For development, run `npm run dev` and copy or link `manifest.json`, `main.js`, and `styles.css` into `<vault>/.obsidian/plugins/cauco/`. Enable the plugin in Obsidian, then use the ribbon icon or the **Open Cauco Dashboard** command.

## Local core

```bash
cd core
python3.11 -m venv .venv
.venv/bin/pip install -e '.[dev]'
source .venv/bin/activate
uvicorn cauco_core.main:app --host 127.0.0.1 --port 8765 --reload
```

Open `http://127.0.0.1:8765/health` to verify it. Override the brain directory with `CAUCO_BRAIN_DIR=/path/to/brain`; the default is this repository's `brain-template/` directory.

## Local Ollama

Inspect models already installed on the machine:

```bash
ollama list
```

Start the local Ollama server if it is not already running:

```bash
ollama serve
```

Cauco defaults to `http://127.0.0.1:11434` and `llama3.1:latest`. The default model is configuration, not a claim that it is installed. Select any discovered local model in the Cauco plugin settings or dashboard.

Environment overrides:

```bash
CAUCO_AI_PROVIDER=ollama
CAUCO_OLLAMA_BASE_URL=http://127.0.0.1:11434
CAUCO_DEFAULT_MODEL=qwen2.5-coder:7b
CAUCO_AI_REQUEST_TIMEOUT=60
CAUCO_AI_TEMPERATURE=0.1
CAUCO_AI_MAX_OUTPUT_TOKENS=1024
```

The Ollama URL is restricted to local HTTP addresses. Ollama requires no API key.

## Python foundations

Install the local packages into the same development environment, then run all checks from the repository root:

```bash
core/.venv/bin/pip install -e ./agents -e ./tools -e ./scheduler
core/.venv/bin/pytest core/tests agents/tests tools/tests scheduler/tests
core/.venv/bin/ruff check core/src core/tests agents/src agents/tests tools/src tools/tests scheduler/src scheduler/tests
```

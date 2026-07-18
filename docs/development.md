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
.venv/bin/pip install -e ../agents -e '.[dev]'
source .venv/bin/activate
uvicorn cauco_core.main:app --host 127.0.0.1 --port 8765 --reload
```

Open `http://127.0.0.1:8765/health` to verify it. Override the brain directory with `CAUCO_BRAIN_DIR=/path/to/brain`; the default is this repository's `brain-template/` directory.

To use a Markdown directory or an Obsidian vault as the read-only brain:

```bash
export CAUCO_BRAIN_DIR="/path/to/brain"
```

Or launch the core with a one-command override:

```bash
CAUCO_BRAIN_DIR="/path/to/brain" \
uvicorn cauco_core.main:app \
  --host 127.0.0.1 \
  --port 8765 \
  --reload
```

For an Obsidian development vault, either point at the vault root or a dedicated directory such as `Cauco Brain/`. Hidden directories are ignored, so `.obsidian/` is never scanned. Cauco reads only visible Markdown files under the configured root. The Memory panel can add tasks, decisions, relationship notes, and project notes only through a server-generated proposal followed by **Apply Change**. **Cancel** does not modify memory, and pending proposals are lost when Cauco Core restarts.

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
CAUCO_MEMORY_MAX_FILE_SIZE=524288
CAUCO_MEMORY_CONTEXT_MAX_FILES=3
CAUCO_MEMORY_CONTEXT_MAX_CHARACTERS=6000
```

The Ollama URL is restricted to local HTTP addresses. Ollama requires no API key.

## Python foundations

Install the local packages into the same development environment, then run all checks from the repository root:

```bash
core/.venv/bin/pip install -e ./agents -e ./tools -e ./scheduler
core/.venv/bin/pytest core/tests agents/tests tools/tests scheduler/tests
core/.venv/bin/ruff check core/src core/tests agents/src agents/tests tools/src tools/tests scheduler/src scheduler/tests
```

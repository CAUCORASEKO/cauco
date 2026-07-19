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
.venv/bin/pip install -e ../agents -e ../tools -e '.[dev]'
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
CAUCO_AGENT_PLAN_REVIEW_TTL_SECONDS=1800
CAUCO_AGENT_PLAN_REVIEW_MAX_RECORDS=100
CAUCO_WORKSPACE_DIR=/path/to/bounded/workspace
CAUCO_EXECUTION_MAX_RECORDS=100
CAUCO_EXECUTION_MAX_FILE_BYTES=1000000
```

The Ollama URL is restricted to local HTTP addresses. Ollama requires no API key.

## Python foundations

Install the local packages into the same development environment, then run all checks from the repository root:

```bash
core/.venv/bin/pip install -e ./agents -e ./tools -e ./scheduler
core/.venv/bin/pytest core/tests agents/tests tools/tests scheduler/tests
core/.venv/bin/ruff check core/src core/tests agents/src agents/tests tools/src tools/tests scheduler/src scheduler/tests
```

Inspect deterministic agent planning without enabling execution:

```bash
curl -s http://127.0.0.1:8765/api/agents/plan \
  -H 'Content-Type: application/json' \
  -d '{"instruction":"What should I work on next in Cauco?"}'

curl -s http://127.0.0.1:8765/api/agents/plan \
  -H 'Content-Type: application/json' \
  -d '{"instruction":"Research MCP for Cauco","include_context":false}'
```

These endpoints read only bounded registered memory through Cauco Core. Plans are deterministic templates; Git repositories and external research sources are not inspected.

Create, inspect, and approve a process-local plan review:

```bash
REVIEW_JSON=$(curl -s http://127.0.0.1:8765/api/agents/plan-reviews \
  -H 'Content-Type: application/json' \
  -d '{"instruction":"What should I work on next in Cauco?","ttl_seconds":1800}')
REVIEW_ID=$(printf '%s' "$REVIEW_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["review_id"])')

curl -s "http://127.0.0.1:8765/api/agents/plan-reviews/$REVIEW_ID"
curl -s -X POST "http://127.0.0.1:8765/api/agents/plan-reviews/$REVIEW_ID/approve" \
  -H 'Content-Type: application/json' \
  -d '{"reviewer_note":"Reviewed for possible future execution."}'
```

The approved response must still show `execution_performed: false`; no plan step or tool ran. Review records, including terminal records, are held only in memory and disappear whenever Cauco Core restarts.

Inspect tool contracts without executing them:

```bash
curl -s http://127.0.0.1:8765/api/tools
curl -s http://127.0.0.1:8765/api/tools/git/operations
curl -s http://127.0.0.1:8765/api/tools/validate \
  -H 'Content-Type: application/json' \
  -d '{"tool_id":"git","operation_id":"status"}'
```

These endpoints return catalog metadata only; they never invoke a runtime adapter.

Phase 6B uses real adapters only when `CAUCO_WORKSPACE_DIR` is explicitly configured. Start with a temporary Git repository:

```bash
TEST_WORKSPACE=$(mktemp -d)
git -C "$TEST_WORKSPACE" init
CAUCO_WORKSPACE_DIR="$TEST_WORKSPACE" uvicorn cauco_core.main:app \
  --host 127.0.0.1 --port 8765
```

After creating and approving a Git plan review, create an inert execution record and explicitly execute one stored step:

```bash
curl -s http://127.0.0.1:8765/api/executions \
  -H 'Content-Type: application/json' \
  -d '{"review_id":"planrev_..."}'

curl -s http://127.0.0.1:8765/api/executions/exec_.../steps/2/execute \
  -H 'Content-Type: application/json' \
  -d '{"timeout_seconds":5,"max_output_chars":20000}'
```

The first call performs nothing. The second runs only the exact approved read-only step. Tests always use temporary workspaces and repositories.

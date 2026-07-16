# Development

## Requirements

- Node.js 20 or newer and npm
- Python 3.11 or newer
- Obsidian desktop for manual plugin testing

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
.venv/bin/cauco-core
```

Open `http://127.0.0.1:8765/health` to verify it. Override the brain directory with `CAUCO_BRAIN_DIR=/path/to/brain`; the default is this repository's `brain-template/` directory.

## Python foundations

Install the local packages into the same development environment, then run all checks from the repository root:

```bash
core/.venv/bin/pip install -e ./agents -e ./tools -e ./scheduler
core/.venv/bin/pytest core/tests agents/tests tools/tests scheduler/tests
core/.venv/bin/ruff check core/src core/tests agents/src agents/tests tools/src tools/tests scheduler/src scheduler/tests
```

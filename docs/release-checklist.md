# Cauco 0.1.0 release-candidate checklist

## Before packaging

- [ ] Use Python 3.11+ and Node.js 20+.
- [ ] Create a fresh Python environment and install `agents`, `tools`, `scheduler`, and `core` in editable mode.
- [ ] Run the backend test suite and Ruff checks.
- [ ] Run `npm install`, `npm run typecheck`, `npm test`, and `npm run build` in `plugin/`.
- [ ] Confirm `git diff --check` and verify that no `.env`, database, cache, or build artifact is tracked.

## Manual Obsidian smoke test

- [ ] Copy `plugin/manifest.json`, `plugin/main.js`, and `plugin/styles.css` into a disposable vault plugin directory.
- [ ] Start Core with a temporary brain, SQLite path, and workspace.
- [ ] Verify health, status, planning, explicit review, inert execution creation, one-step execution, verification, experience consolidation, candidate review, promotion, memory proposal preview/confirmation, guidance, reflection, and terminal cycle state.
- [ ] Restart Core between lifecycle stages and confirm persisted SQLite records restore correctly.
- [ ] Confirm unavailable Core, malformed responses, stale state, conflict, expired, and validation errors are presented without private payloads.

## Release boundaries

Implemented: local Core, Obsidian dashboard, explicit human-guided lifecycle actions, bounded memory and learning observability, and allowlisted execution/mutation safeguards.

Experimental: local Ollama chat and the broader execution/mutation controls require a disposable workspace for manual validation.

Planned: remote operation, authentication, background jobs, autonomous workflows, semantic memory, and publishing/distribution automation.

# Architecture

Cauco currently consists of independent UI and local-service components plus model-independent Python domain packages.

```text
Obsidian plugin (TypeScript)
        |
        | local, read-only HTTP
        v
Cauco Core (FastAPI) ------> configured Markdown brain

Python domain foundations (no runtime loop)
  |-- agent contract + Operations Agent registry
  |-- permission-aware tool registry
  `-- scheduler job-definition registry
```

The plugin and core deliberately do not share executable code. Their boundary is the documented JSON contract in [api-contract.md](api-contract.md), with defensive validation on both sides.

## Component responsibilities

- `plugin/` renders observable state, stores the local core URL, and degrades to deterministic offline cards.
- `core/` owns HTTP transport, configuration, safe memory discovery, and assembled status responses.
- `brain-template/` is portable user-owned Markdown suitable for copying into an Obsidian vault.
- `agents/`, `tools/`, and `scheduler/` define small contracts and registries. They do not run autonomous loops.
- `installer/` remains reserved for a later packaging milestone.

The source uses no architecture-specific binaries, so Apple Silicon and Intel are supported at source level.

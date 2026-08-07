# Security boundaries

The current release keeps data and inference local. Deterministic foundations remain separate from the opt-in local Ollama chat path.

## Current boundaries

The macOS Host exposes the Native Capability Broker only to its owned Core child through a private owner-only Unix domain socket. The socket path and cryptographically random bearer token are ephemeral, passed only through the child environment, never persisted or exposed in diagnostics/API responses, and each connection accepts one bounded JSON request. The Host validates the token before dispatching the typed allowlist; `contacts.status` is the only implemented native operation and no contact records are transported.

- Cauco Core binds to `127.0.0.1` by default. Its AI routes add model discovery and one validated chat POST endpoint.
- CORS permits a small explicit set of local Obsidian/development origins and only GET and POST methods.
- Memory access is limited to visible Markdown under one configured directory. Paths are relative, traversal is rejected, hidden directories are pruned, and symlinks are not followed.
- Individual reads enforce a configurable maximum size and strict UTF-8 decoding. Search skips unreadable and oversized files.
- File content is exposed through bounded core APIs. Memory insertion is limited to four allowlisted files and existing approved headings, and requires a stored proposal followed by explicit confirmation. No arbitrary update, rename, move, or delete route exists.
- Tool definitions remain immutable metadata. Runtime policy allows the three read-only operations plus only `memory.create_proposal`, `memory.confirm_proposal`, `filesystem.write_text_file`, and exact-path `git.add` through the preview-first mutation path. All other mutations remain denied.
- Git uses dedicated adapters only: fixed `git.status` and fixed `git add -- <approved paths>`, always with `shell=False`, a bounded environment, explicit workspace, and no client arguments.
- The scheduler stores validated definitions but runs nothing.
- The Operations Agent formats structured data and does not call a model.
- Project, Git, and Research agent routing uses fixed local signals. These agents return proposal-only results and cannot invoke tools, subprocesses, network access, or memory confirmation APIs.
- Agent planning reads only visible objects already registered by the Memory Engine and uses its bounded safe reader. Client requests cannot provide paths or memory IDs. Excerpts are capped per item and at 7,000 total characters, retain relative provenance only, and are treated as inert untrusted data.
- Agent plan review stores an immutable snapshot behind an opaque identifier. Human notes remain inert, every decision verifies a canonical SHA-256 digest, and a lock permits only one terminal transition. Approval does not execute tools, plan steps, Git, shell commands, network calls, memory writes, or models.
- The configured Ollama URL must use HTTP on `127.0.0.1`, `localhost`, or `::1`; requests cannot override it.
- Chat accepts only a bounded message and optional validated model name. The system prompt and generation options are controlled by core configuration.
- When enabled, chat sends the submitted message, fixed system prompt, and only bounded relevant Markdown context to local Ollama. Exact source paths are returned.
- Memory content is untrusted reference data in a separately delimited user-message section. The system prompt tells the model to ignore instructions inside memory, avoid freshness claims without support, cite relevant file names, and never claim memory was updated.
- Provider errors are converted to bounded messages without internal exception traces.
- Ollama local access uses no API key and no secret is stored.

## Explicitly out of scope

There is no authentication, remote/cloud AI provider, unrestricted shell access, generic tool executor, external connector execution, autonomous workflow, background daemon, email sending, calendar mutation, microphone or webcam access, wake-word listener, persistent chat history, arbitrary or AI-driven memory writing, automatic summarization, embeddings, vector database, semantic search, long-term memory extraction, model-driven tool or agent execution, or streaming. Confirmed allowlisted memory insertions are atomic, backed up once per target, and never originate from chat.

Plan reviews are process-local and disappear on restart. Approval authorizes only the stored plan snapshot for possible future execution; future step/tool confirmation and the separate memory-write confirmation contract are still required. The plugin's core URL is configurable for development, but localhost remains the safe default. Pointing it at a remote service changes the trust boundary and is not supported by this release.

Workspace text writes accept only `.md`, `.txt`, `.json`, `.yaml`, `.yml`, and `.toml`, with a configurable 20,000-character default and 100,000-character hard contract limit. Absolute/traversal paths, symlinks, hidden or secret paths, `.git`, environment/key/certificate files, editor temporaries, non-regular files, source code, manifests, dependency/lock files, Docker/CI configuration, and missing parents are blocked. Existing content is digest-bound at preview time. Replacement creates a bounded internal rotating backup before atomic replacement; verification failure restores the backup or removes a failed create where possible.

Mutation confirmations are single-use and compare the immutable preview digest plus an exact operation-specific phrase. Audit events record lifecycle outcomes and safe metadata only: no full content, phrases, secrets, environment data, absolute paths, or backup paths.

## Execution boundary

- A configured `CAUCO_WORKSPACE_DIR` is required. `/`, the home directory, and broad system roots are rejected.
- Paths are workspace-relative, canonicalized, traversal-resistant, and checked against symlink escape. `.env`, SSH/cloud/credential directories, keys, certificates, token-named files, and hidden directory entries are blocked.
- `git.add` accepts only immutable approved relative paths. It rejects wildcards, directories, symlinks, ignored/sensitive/binary/oversized files, partial staging, deletions, and complex Git states. Preview binds index and worktree digests; execution backs up and verifies the index. Locks and preview stores are process-local, so external index changes are detected as stale rather than serialized by Cauco.
- Text reads require regular UTF-8 files, reject binary and oversized files, and enforce character limits. Directory listings are deterministic, bounded, hide sensitive entries, and do not follow symlinks.
- Execution time and output size are bounded. API and audit data use relative paths and safe messages; environment variables, absolute paths, and file contents are not copied into audit events.
- Every accepted execution record and step transition is audited. Denied step attempts are recorded without claiming execution.
- The Obsidian plugin is only a control surface. It uses the configured Core URL, has no subprocess or direct host-filesystem access, never replaces stored step fields, never approves or executes automatically, and never writes execution output into settings or the vault.
- Returned file content, Git output, and audit data are bounded and inserted as text, never HTML or executable Markdown. Client error and display sanitizers redact host-style absolute paths.

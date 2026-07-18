# Security boundaries

The current release keeps data and inference local. Deterministic foundations remain separate from the opt-in local Ollama chat path.

## Current boundaries

- Cauco Core binds to `127.0.0.1` by default. Its AI routes add model discovery and one validated chat POST endpoint.
- CORS permits a small explicit set of local Obsidian/development origins and only GET and POST methods.
- Memory access is limited to visible Markdown under one configured directory. Paths are relative, traversal is rejected, hidden directories are pruned, and symlinks are not followed.
- Individual reads enforce a configurable maximum size and strict UTF-8 decoding. Search skips unreadable and oversized files.
- File content is exposed through bounded core APIs. Memory insertion is limited to four allowlisted files and existing approved headings, and requires a stored proposal followed by explicit confirmation. No arbitrary update, rename, move, or delete route exists.
- All registered tools declare permission metadata and are currently read-only.
- The Git tool is a placeholder and does not invoke Git or a shell.
- The scheduler stores validated definitions but runs nothing.
- The Operations Agent formats structured data and does not call a model.
- Project, Git, and Research agent routing uses fixed local signals. These agents return proposal-only results and cannot invoke tools, subprocesses, network access, or memory confirmation APIs.
- Agent planning reads only visible objects already registered by the Memory Engine and uses its bounded safe reader. Client requests cannot provide paths or memory IDs. Excerpts are capped per item and at 7,000 total characters, retain relative provenance only, and are treated as inert untrusted data.
- The configured Ollama URL must use HTTP on `127.0.0.1`, `localhost`, or `::1`; requests cannot override it.
- Chat accepts only a bounded message and optional validated model name. The system prompt and generation options are controlled by core configuration.
- When enabled, chat sends the submitted message, fixed system prompt, and only bounded relevant Markdown context to local Ollama. Exact source paths are returned.
- Memory content is untrusted reference data in a separately delimited user-message section. The system prompt tells the model to ignore instructions inside memory, avoid freshness claims without support, cite relevant file names, and never claim memory was updated.
- Provider errors are converted to bounded messages without internal exception traces.
- Ollama local access uses no API key and no secret is stored.

## Explicitly out of scope

There is no authentication, remote/cloud AI provider, unrestricted shell access, external connector, autonomous workflow, background daemon, email sending, microphone or webcam access, wake-word listener, persistent chat history, arbitrary or AI-driven memory writing, automatic summarization, embeddings, vector database, semantic search, long-term memory extraction, model-driven tool or agent execution, or streaming. Confirmed allowlisted memory insertions are atomic, backed up once per target, and never originate from chat.

The plugin's core URL is configurable for development, but localhost remains the safe default. Pointing it at a remote service changes the trust boundary and is not supported by this release.

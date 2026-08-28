# World Monitor → Cauco architecture audit

Date: 2026-08-28  
Reference: local `worldmonitor-main/` checkout; source was inspected read-only.

## Executive conclusion

World Monitor is valuable as an external, read-only intelligence provider, not
as a Cauco runtime dependency or copied subsystem. The safest boundary is a
Cauco provider adapter that calls a small allowlisted World Monitor REST/MCP
surface, validates and freshness-bounds the result, and returns advisory
context to Cauco reasoning. World Monitor must never receive Cauco tool,
execution, mutation, native-broker, or private-brain authority.

The strongest immediate use is external context for questions such as what
could affect Antü Magallanes: country risk, energy, infrastructure/cable,
weather/natural events, shipping/chokepoints, aviation, cyber, and relevant
news. These are evidence inputs, not decisions.

## 1. World Monitor architecture map

The documented topology in `ARCHITECTURE.md` is a TypeScript SPA plus API
routes, Vercel edge deployment, Railway relays/seeders, Upstash Redis,
Convex for account/entitlement and intelligence history, and a Tauri 2
desktop shell with a Node sidecar. The browser calls `/api/*`; seeded data is
generally read from caches rather than fetched directly by the UI. The same
overview appears in `README.md` (“Tech Stack”, “Deployment Topology”).

Important boundaries observed in code:

- `server/gateway.ts` maps API paths to cache tiers and wraps route behavior
  with cache/error/rate-limit policy.
- `api/mcp/handler.ts`, `api/mcp/dispatch.ts`, and `api/mcp/registry/index.ts`
  implement the MCP protocol and public tool registry.
- `api/mcp/registry/{cache-tools,rpc-tools,nlp-tools,source-tools}.ts` split
  cached reads, RPC-backed operations, NLP utilities, and source metadata.
- `src-tauri/src/main.rs` owns desktop commands, persistent cache, keychain
  secrets, sidecar startup, and renderer IPC. This is a larger desktop
  privilege surface than Cauco’s deliberately narrow Native Broker.

The data flow is therefore:

```text
upstream feeds/APIs → seeders/relays → Redis/cache → API/MCP → SPA/panels
                                                        ↘ SDK/CLI/agents
```

World Monitor also has static geographic abstractions. For example,
`src/config/geo-map.ts` supplies curated geography and
`src/services/cable-activity.ts` derives nearby cable warnings from that
registry and incoming warnings. This is useful context modeling, but should
not be copied as a Cauco data store.

## 2. Data and intelligence sources

The source catalog is registry-driven: `src/config/feeds.ts` defines canonical
feeds and source metadata, while `server/_shared/source-tiers.ts` and
`server/_shared/fetch-json.ts` apply source/fetch policy. The repository
contains sources across news, conflicts, finance, energy, climate, natural
events, cyber, aviation, maritime, infrastructure, and supply chain. The
README names examples such as Finnhub, Yahoo, GDELT, ACLED, UCDP, FIRMS,
OpenSky, FRED, CoinGecko, and external relays.

This is a mixture of public feeds, public APIs, partner data, and credentialed
third-party services. Availability and licensing vary by source. `SELF_HOSTING.md`
lists required secrets and explicitly distinguishes no-key, signup, paid, and
optional feeds.

Caching is a first-class design: `server/gateway.ts` assigns route tiers;
`server/_shared/redis.ts`, `server/_shared/fetch-json.ts`, and the seed/meta
health code support freshness and degradation; `server/_shared/rate-limit.ts`
defines route-specific limits. Cauco should consume freshness metadata when
available and treat stale, empty, or unavailable responses as uncertainty—not
as current fact.

Useful independent patterns for Cauco are source attribution, freshness
contracts, bounded response schemas, explicit source tiers, and graceful
degradation. World Monitor’s scale of upstream ingestion is not a reason to
put a general crawler inside Cauco.

## 3. MCP, API, and SDK

The README identifies:

- MCP Streamable HTTP at `/mcp`; `tools/list` is public, while data-bearing
  `tools/call` operations generally require `X-WorldMonitor-Key` or OAuth.
- REST at `https://api.worldmonitor.app`, described by the repository’s
  OpenAPI documentation under `docs/api/`.
- CLI source under `cli/` and SDKs under `sdk/`.

`api/mcp/registry/index.ts` constructs `TOOL_REGISTRY` and deliberately strips
internal `_` fields before exposing public schemas. `api/mcp/auth.ts` resolves
authentication, entitlement, and rate limits; `api/mcp/dispatch.ts` performs
tool dispatch, freshness handling, quotas, and telemetry. `cli/src/core.mjs`
shows the exact MCP methods (`tools/list`, `tools/call`, `prompts/list`, and
`resources/list`) and argument forwarding. `sdk/ruby/lib/worldmonitor.rb` is a
particularly clear zero-dependency client reference with `call_tool`,
`country_risk`, and MCP auth behavior.

The MCP surface is intentionally broad: it includes generic `call_tool(name,
arguments)` in the SDK and a large registry. Cauco should not expose that
generic freedom to its own agents. A Cauco adapter should allowlist named
provider operations, map fixed typed inputs to exact upstream calls, cap
result size, strip unsupported fields, preserve source/freshness metadata, and
never forward arbitrary MCP tool names from agent output.

REST is preferable where a stable read-only endpoint exists because it avoids
importing a broad MCP registry into Cauco. MCP is a viable external fallback
only behind the same fixed operation map and explicit credentials.

## 4. Correlation and situational intelligence

There is real implemented correlation, but it is a layered collection of
bounded domain algorithms rather than a single autonomous intelligence brain.

- `src/services/cross-module-integration.ts` defines alert families including
  convergence, CII spikes, cascades, sanctions, radiation, and composites.
- `src/services/related-assets.ts` scores keyword/asset matches and connects
  stories to facilities, cables, and other map assets.
- `src/services/military-vessels.ts` contains `clusterVessels`, which clusters
  vessel observations into hotspots; this is concrete spatial aggregation.
- `server/_shared/brief-render.js` validates story envelopes, cluster identity,
  multi-source counts, and rendered brief inputs.
- `src/services/cached-risk-scores.ts` validates and canonicalizes CII scores,
  levels, trends, contributors, and timestamps.
- `api/mcp/registry/nlp-tools.ts` and `rpc-tools.ts` expose implemented NLP/
  analysis utilities such as clustering or extraction where registered.

The marketing phrase “cross-stream correlation” should therefore be read as
implemented signal joins, clustering, score derivation, and presentation
contracts—not as evidence that an LLM has authoritative causal knowledge.
The reusable concept for Cauco is a provenance-preserving evidence graph and
deterministic correlation layer. The scoring policy itself should be
reimplemented independently so Cauco can align it with local brain context,
human review, and fail-closed semantics.

## 5. Local AI and Ollama

`server/_shared/llm.ts` supports Ollama and other configured OpenAI-compatible
providers, with hostname allowlisting and provider selection. The frontend
settings flow in `src/components/RuntimeConfigPanel.ts` discovers configured
Ollama models; `server/worldmonitor/news/v1/summarize-article.ts` and
`server/worldmonitor/intelligence/v1/deduction-prompt.ts` show local/provider
LLM use for summaries and intelligence deductions. `SELF_HOSTING.md` documents
`LLM_API_URL`, `LLM_API_KEY`, and `LLM_MODEL` configuration.

The useful pattern is provider-neutral prompt construction, bounded source
context, sanitization (`server/_shared/llm-sanitize.js`), and explicit provider
configuration. The model produces summaries/assessments; the data contracts,
freshness checks, and route policies remain authoritative. Cauco should retain
this separation and place any LLM answer inside its advisory reasoning layer,
never in ToolRegistry or execution policy.

## 6. Desktop/Tauri compared with Cauco Native Broker

World Monitor’s `src-tauri/src/main.rs` has useful concepts: a desktop-only
privilege boundary, explicit command registration, bounded cache writes in
`cache_bounds.rs`, keychain-backed secrets, sidecar ownership, and shutdown
cleanup. These are conceptual references only.

It also has a much broader renderer IPC and persistence surface, including
generic cache entry operations and URL/process/sidecar concerns. That breadth
is inappropriate for Cauco’s safety model. Cauco should copy the ideas of
explicit command allowlists, bounded inputs, ownership, and lifecycle cleanup,
while keeping OS operations behind the existing capability registry and
Native Broker. World Monitor source must not be copied into Cauco.

## 7. Security and permissions

World Monitor’s external calls include upstream feeds, API-key services,
Redis/Upstash, Convex, relays, and optional LLM providers. Its deployment
requires multiple secrets; `SELF_HOSTING.md` warns about relay authentication,
trusted proxy CIDRs, API-key quotas, and disabling auth only for local debug.
`server/_shared/rate-limit.ts`, `api/mcp/auth.ts`, and
`server/gateway.ts` are the relevant controls.

For Cauco, risks include stale or incorrectly attributed external data,
credential leakage, rate-limit coupling, prompt injection in retrieved news,
and importing a broad generic MCP invocation surface. A provider adapter must
use explicit allowlists, short timeouts, bounded JSON, source URLs/timestamps,
secret isolation, and prompt sanitization. Retrieved text is untrusted data,
not instructions. External data must never be allowed to select a Cauco tool
or mutation.

## 8. Licensing

`worldmonitor-main/LICENSE`, `README.md`, and `package.json` identify the
project as AGPL-3.0-only. The README says commercial use is possible only
under AGPL obligations or a separate commercial arrangement, and separately
notes trademark/branding restrictions.

Classification:

- Safe to study: repository behavior, interfaces, documented concepts, and
  publicly observable API semantics.
- Potentially safe to invoke externally: public/read-only API or MCP calls,
  subject to service terms, authentication, rate limits, attribution, and
  upstream data licenses.
- Safe to reproduce independently: general ideas such as freshness tiers,
  bounded provider adapters, provenance, deterministic clustering, and
  explicit desktop command boundaries.
- Not safe to copy directly into proprietary Cauco without legal review:
  source code, substantial code structure, generated assets, branded UI, or
  derivative server components. AGPL obligations can attach to derivative or
  combined software; obtain legal advice before embedding or modifying it.

## 9. Cauco opportunity matrix

| Classification | Finding | Recommendation |
|---|---|---|
| A — Integrate externally | Read-only country risk, news, energy, infrastructure/cable, weather, shipping, aviation, cyber, and conflict endpoints where actual API contracts support them | One typed provider adapter; freshness and provenance required |
| A — Integrate externally | MCP/REST discovery for operator-selected provider configuration | Use fixed allowlisted calls; no generic `tools/call` passthrough |
| B — Reimplement independently | Evidence normalization, freshness states, source confidence, regional impact mapping | Keep in Cauco’s provider-neutral connector layer |
| B — Reimplement independently | Correlation and impact scoring | Tie to Antü/brain context and human review; do not import World Monitor scoring code |
| C — Inspiration only | Multi-panel situational dashboard, map-layer registry, Tauri lifecycle patterns | Reproduce concepts only if they fit Cauco’s UI and permissions |
| D — Not useful | World Monitor’s broad frontend, variant system, billing, and operational seed fleet | Keep separate |
| E — Avoid/法律 review | Vendoring AGPL implementation or exposing its generic MCP registry to agents | External service boundary or separate implementation only |

## 10. Proposed Cauco world-intelligence boundary

```text
Cauco agent/reasoning
  → bounded WorldIntelligenceProvider
  → fixed provider adapter
  → World Monitor REST/MCP or another provider
```

Suggested provider-neutral contracts:

```text
WorldIntelligenceQuery {
  subject: bounded location/topic identifier
  categories: allowlisted category set
  time_window: bounded interval
  max_items: bounded integer
}

WorldIntelligenceResult {
  items: bounded evidence records
  source: provider/source identifier
  retrieved_at: timestamp
  source_published_at: timestamp | null
  freshness: fresh | stale | unavailable
  confidence: bounded advisory value | null
  limitations: bounded strings
}
```

Only expose operations supported by the inspected World Monitor surface and
selected after OpenAPI/MCP schema pinning. Candidate names are:

- `world.news.search`
- `world.events.recent`
- `world.country.risk`
- `world.infrastructure.status`
- `world.energy.context`
- `world.market.context`
- `world.conflicts.status`
- `world.weather.context`
- `world.shipping.context`
- `world.aviation.context`
- `world.cyber.incidents`

These are proposed Cauco names, not claims that every route has identical
coverage or semantics. The adapter must map each only when the exact upstream
contract exists. No operation should be registered as a mutation, execution
tool, native capability, or unrestricted MCP proxy.

## 11. Antü Magallanes use case

For “What external developments could affect Antü Magallanes today?”, the
highest-value implemented World Monitor families are:

- country/geopolitical risk via CII/risk-score surfaces;
- energy prices, supply, disruptions, chokepoints, and energy-shock data;
- infrastructure and submarine-cable geography/health;
- weather, natural disasters, wildfire, and climate signals;
- maritime/shipping and strategic-waterway context;
- aviation delays/closures where relevant to logistics;
- cyber-threat feeds;
- attributed news and conflict/event feeds.

The repository supports these domains through route families visible in
`server/gateway.ts` and corresponding RPC implementations under
`server/worldmonitor/` and `api/*/v1/`. The cable implementation is concrete
in `src/services/cable-activity.ts`; CII validation is concrete in
`src/services/cached-risk-scores.ts`; energy/chokepoint registries are in
`server/_shared/chokepoint-registry.ts`.

What is not established by this audit is a ready-made Antü-specific impact
model, local supplier graph, or causal forecast. Cauco would need to combine
external evidence with its own Markdown brain and explicit user context, then
label inferences clearly. World Monitor evidence should remain cited,
timestamped, and advisory.

## 12. Recommended next step

Implement one read-only provider-neutral proof of concept for:

```text
WorldIntelligenceProvider.countryRisk(countryCode)
```

Use a pinned World Monitor REST endpoint or a fixed MCP tool mapping, with
bounded timeout, authentication isolated from agents, strict response
validation, freshness/provenance fields, and a safe unavailable result. Test
it with a fake provider and ensure it cannot reach ToolRegistry, execution,
mutation, or Native Broker. Only after this contract is stable should energy,
cable, or news adapters be added.

## Files inspected

At minimum: `README.md`, `ARCHITECTURE.md`, `CONCEPTS.md`, `SELF_HOSTING.md`,
`package.json`, `LICENSE`; `api/mcp/handler.ts`, `api/mcp/auth.ts`,
`api/mcp/dispatch.ts`, `api/mcp/registry/index.ts`,
`api/mcp/registry/{cache-tools,rpc-tools,nlp-tools,source-tools}.ts`,
`server/gateway.ts`, `server/_shared/{fetch-json,rate-limit,llm,llm-sanitize}.ts/js`,
`src/config/feeds.ts`, `src/services/{cross-module-integration,related-assets,
cable-activity,military-vessels,cached-risk-scores}.ts`, `cli/src/core.mjs`,
`sdk/ruby/lib/worldmonitor.rb`, and `src-tauri/src/main.rs`/
`src-tauri/src/cache_bounds.rs`.

## Final status

- Files changed: `docs/research/worldmonitor-cauco-audit.md` only.
- `worldmonitor-main` was not modified, copied, vendored, or added as a
  dependency.
- No Cauco production code, tools, agents, reasoning, or Native Broker code
  was changed.
- No commit or push was performed.

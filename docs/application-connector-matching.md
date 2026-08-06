# Application connector matching v1

Matching relates an observed application bundle to an explicit provider mapping and, separately, to registered connector metadata. It uses exact bundle identifiers only. A mapped provider is not a registered connector; a registered connector is not authorized, connected, routable, healthy, or executable.

Matching is explicitly refreshed from the current in-memory inventory and connector registry. It does not rescan applications, register connectors, evaluate permissions, invoke routing, launch applications, inspect processes, or read private data. Display names and interface languages do not affect matching. Ambiguous registered candidates remain ambiguous.

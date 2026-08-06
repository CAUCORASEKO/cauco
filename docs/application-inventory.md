# Mac application inventory v1

The inventory is an observational, explicitly refreshed snapshot of `.app` bundles under `/Applications`, `/System/Applications`, `/System/Applications/Utilities`, and `~/Applications` when those roots exist. It reads only an allowlist from `Contents/Info.plist`; it does not launch applications, inspect processes, read private data, request permissions, or register connectors.

Installed, available, authorized, connected, and controllable are separate states. Availability means only that safe metadata could be read. Authorization and connection require future permission-aware connectors. Inventory refresh is bounded, deterministic, does not monitor the filesystem, and ignores hidden entries and symlinked bundles. Duplicate bundle identifiers resolve deterministically by path.

Display names are preserved, while matching uses Unicode-safe normalized metadata. Machine-readable states and fields remain independent of localized presentation. Connector association hints are intentionally not implemented in v1; discovering an application never implies a connector or capability exists.

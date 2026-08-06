# Connector runtime

Cauco separates applications (installed products), connectors (authorized integration implementations), capabilities (stable machine-readable actions), permissions (operating-system or provider grants), and runtime requests (immutable requests to resolve a capability). Installed does not mean authorized, and resolution never executes an action.

IDs, states, reason codes, and policy are language-neutral. Locale metadata is preserved separately for interface, request, and response presentation; localization is a future concern. Connector selection is deterministic and prefers an explicit connector, then availability, permission readiness, configured priority, and connector ID.

Future integrations should prefer an official API/native integration, then AppleScript/JXA/Shortcuts, trusted CLI, Accessibility API, and visual automation only as a last resort. Each connector remains behind the permission, confirmation, audit, and execution boundaries; this v1 performs metadata inspection only.

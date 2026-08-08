# Apple Contacts read connector v1

The connector is metadata-registered as `apple_contacts.local` / `apple_contacts` and exposes only `contacts.search`, `contacts.get`, and `contacts.list_limited` metadata. On unsupported platforms or without a native bridge it is registered as unavailable. Startup performs no permission request and reads no contacts.

`contacts.search` is the first real native personal-data capability. When the authenticated Unix-socket broker is configured, search uses `CNContactStore` through the Swift host, is read-only, explicit-request-only, and returns at most 20 bounded sanitized results. There are no startup reads or permission prompts. The host currently uses the supported name predicate; it does not enumerate the complete address book for cross-field matching. The injected gateway remains available for tests and does not get silently replaced or bypassed.

`contacts.get` is also implemented and accepts only a Host-issued opaque reference from the current Host lifetime. The Host keeps a bounded, ephemeral in-memory reference-to-native-identifier mapping; it is never persisted or sent over IPC. Unknown or stale references fail closed.

`contacts.list_limited` is implemented as an explicit, read-only operation with a maximum of 20 contacts. Native enumeration stops at the requested bound; the full address book is never loaded. Listed references are registered for `contacts.get` and remain ephemeral.

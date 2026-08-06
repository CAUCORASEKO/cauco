# Apple Contacts read connector v1

The connector is metadata-registered as `apple_contacts.local` / `apple_contacts` and exposes only `contacts.search`, `contacts.get`, and `contacts.list_limited` metadata. On unsupported platforms or without a native bridge it is registered as unavailable. Startup performs no permission request and reads no contacts.

The native boundary is an injected gateway. A production macOS gateway can be added behind this boundary using `CNContactStore`; this implementation has no AppleScript, shell, SQLite, UI automation, or database fallback. Permission is requested only through the explicit permission endpoint. Search first resolves through the existing connector runtime and then sanitizes bounded name, organization, email, and phone fields. Results are ephemeral and are not written to memory, SQLite, or learning systems.

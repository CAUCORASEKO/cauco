# Apple Calendar connector

Calendar read v1 is complete: status, bounded calendar listing, event range reads, and `events.get` are broker-backed. `events.get` accepts only Host-issued ephemeral `event_reference` values and performs an exact EventKit lookup; it never enumerates all events. Calendar and event native identifiers remain inside the Host, and references are in-memory only for the current Host lifetime. No Calendar write capabilities exist.

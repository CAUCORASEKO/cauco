# Apple Calendar connector

Calendar read v1 is complete: status, bounded calendar listing, event range reads, and `events.get` are broker-backed. `events.get` accepts only Host-issued ephemeral `event_reference` values and performs an exact EventKit lookup; it never enumerates all events. Calendar and event native identifiers remain inside the Host, and references are in-memory only for the current Host lifetime. No Calendar write capabilities exist.

`calendar.events.create` is the first write capability. It requires an explicit confirmed request, a bounded closed payload, and a writable selected/default calendar. Creation is Host-owned, idempotent for the Core request lifetime, and excludes attendees, alarms, recurrence, URLs, and attachments. No startup, background, or automatic writes occur.

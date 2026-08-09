from dataclasses import dataclass
import re
from datetime import datetime

_REFERENCE = re.compile(r"^calendar_[A-Za-z0-9_-]{8,80}$")
_TYPES = {"local", "caldav", "exchange", "subscription", "birthday", "unknown"}

@dataclass(frozen=True, slots=True)
class CalendarSummary:
    calendar_reference: str
    title: str
    source_title: str
    type: str
    allows_content_modifications: bool

    def __post_init__(self):
        if not isinstance(self.calendar_reference, str) or not _REFERENCE.fullmatch(self.calendar_reference): raise ValueError("Invalid calendar reference")
        if any(not isinstance(value, str) or (not value and field != "source_title") or len(value) > 200 or any(ord(c) < 32 for c in value) for field, value in (("title", self.title), ("source_title", self.source_title), ("type", self.type))): raise ValueError("Invalid calendar metadata")
        if self.type not in _TYPES: raise ValueError("Invalid calendar type")
        if not isinstance(self.allows_content_modifications, bool): raise ValueError("Invalid calendar modification flag")

@dataclass(frozen=True, slots=True)
class CalendarEventSummary:
    event_reference: str; calendar_reference: str; title: str; start: str; end: str; all_day: bool; location: str; notes: str
    def __post_init__(self):
        for value, pattern in ((self.event_reference, r"^event_[A-Za-z0-9_-]{8,80}$"), (self.calendar_reference, r"^calendar_[A-Za-z0-9_-]{8,80}$")):
            if not isinstance(value, str) or not re.fullmatch(pattern, value): raise ValueError("Invalid event reference")
        try: starts, ends = datetime.fromisoformat(self.start.replace("Z", "+00:00")), datetime.fromisoformat(self.end.replace("Z", "+00:00"))
        except ValueError as error: raise ValueError("Invalid event dates") from error
        if starts.tzinfo is None or ends.tzinfo is None or ends < starts: raise ValueError("Invalid event dates")
        if any(not isinstance(v, str) or len(v) > n for v, n in ((self.title,300),(self.location,300),(self.notes,1000))) or not isinstance(self.all_day, bool): raise ValueError("Invalid event metadata")

@dataclass(frozen=True, slots=True)
class CalendarEventRangeResponse:
    results: tuple[CalendarEventSummary, ...]; result_count: int; truncated: bool; range_start: str; range_end: str

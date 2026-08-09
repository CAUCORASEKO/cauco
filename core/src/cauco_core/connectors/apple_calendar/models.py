from dataclasses import dataclass
import re

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

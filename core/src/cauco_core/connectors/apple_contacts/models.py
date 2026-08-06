"""Bounded immutable Apple Contacts output models."""

import re
from dataclasses import dataclass
from datetime import datetime

REF = re.compile(r"^contact_[A-Za-z0-9_-]{8,80}$")


def clean(value: str, limit: int = 200) -> str:
    if not isinstance(value, str):
        raise ValueError("Contact text must be a string.")
    value = "".join(char for char in value if ord(char) >= 32 or char in "\t\n")
    return value.strip()[:limit]


@dataclass(frozen=True, slots=True)
class EmailEntry:
    label: str
    address: str
    primary: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", clean(self.label, 50))
        object.__setattr__(self, "address", clean(self.address, 254))


@dataclass(frozen=True, slots=True)
class PhoneEntry:
    label: str
    number: str
    normalized_number: str
    primary: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", clean(self.label, 50))
        object.__setattr__(self, "number", clean(self.number, 80))
        object.__setattr__(self, "normalized_number", clean(self.normalized_number, 80))


@dataclass(frozen=True, slots=True)
class ContactSummary:
    contact_reference: str
    display_name: str
    given_name: str = ""
    family_name: str = ""
    organization: str = ""
    emails: tuple[EmailEntry, ...] = ()
    phones: tuple[PhoneEntry, ...] = ()
    provider_id: str = "apple_contacts"
    fields_returned: tuple[str, ...] = ("name", "organization", "email", "phone")
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not REF.fullmatch(self.contact_reference):
            raise ValueError("Contact reference must be opaque and bounded.")
        for name in ("display_name", "given_name", "family_name", "organization"):
            object.__setattr__(self, name, clean(getattr(self, name)))
        object.__setattr__(self, "emails", tuple(self.emails))
        object.__setattr__(self, "phones", tuple(self.phones))
        object.__setattr__(self, "fields_returned", tuple(sorted(set(self.fields_returned))))
        object.__setattr__(self, "limitations", tuple(self.limitations))


@dataclass(frozen=True, slots=True)
class ContactQuery:
    name: str | None = None
    organization: str | None = None
    email: str | None = None
    phone: str | None = None
    limit: int = 20

    def __post_init__(self) -> None:
        values = [
            value for value in (self.name, self.organization, self.email, self.phone) if value
        ]
        if not values or any(not isinstance(value, str) or not clean(value) for value in values):
            raise ValueError("At least one non-empty contact query is required.")
        if any(len(value) > 200 for value in values) or not 1 <= self.limit <= 50:
            raise ValueError("Contact query is out of bounds.")
        for field_name in ("name", "organization", "email", "phone"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, clean(value))


@dataclass(frozen=True, slots=True)
class ContactSearchResponse:
    query: ContactQuery
    results: tuple[ContactSummary, ...]
    result_count: int
    truncated: bool
    executed_at: datetime
    connector_id: str = "apple_contacts.local"
    provider_id: str = "apple_contacts"
    method: str = "apple-contacts-read-v1"
    limitations: tuple[str, ...] = (
        "Read-only bounded contact data; no private native fields are returned.",
    )

    def __post_init__(self) -> None:
        if self.executed_at.tzinfo is None:
            raise ValueError("Timestamp must be timezone-aware.")
        object.__setattr__(self, "results", tuple(self.results))
        object.__setattr__(self, "limitations", tuple(self.limitations))

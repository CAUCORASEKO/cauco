"""Apple Contacts read-only connector."""

from .connector import AppleContactsConnector
from .models import ContactQuery, ContactSearchResponse, ContactSummary, EmailEntry, PhoneEntry

__all__ = [
    "AppleContactsConnector",
    "ContactQuery",
    "ContactSearchResponse",
    "ContactSummary",
    "EmailEntry",
    "PhoneEntry",
]

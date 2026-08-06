"""Allowlist sanitizer for injected native contact records."""

import hashlib

from .models import ContactSummary, EmailEntry, PhoneEntry, clean


def sanitize(record: dict) -> ContactSummary:
    native_identifier = clean(record.get("identifier", ""), 80)
    reference = "contact_" + hashlib.sha256(native_identifier.encode()).hexdigest()[:24]
    emails = tuple(
        EmailEntry(clean(item.get("label", ""), 50), clean(item.get("address", ""), 254))
        for item in record.get("emails", ())
        if isinstance(item, dict) and item.get("address")
    )
    phones = tuple(
        PhoneEntry(
            clean(item.get("label", ""), 50),
            clean(item.get("number", ""), 80),
            "".join(char for char in item.get("number", "") if char.isdigit() or char == "+"),
        )
        for item in record.get("phones", ())
        if isinstance(item, dict) and item.get("number")
    )
    emails = tuple(dict.fromkeys(emails))
    phones = tuple(dict.fromkeys(phones))
    return ContactSummary(
        reference,
        clean(record.get("display_name", "")),
        clean(record.get("given_name", "")),
        clean(record.get("family_name", "")),
        clean(record.get("organization", "")),
        emails,
        phones,
    )

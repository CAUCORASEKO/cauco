"""Allowlist sanitizer for injected native contact records."""

import hashlib

from .models import REF, ContactSummary, EmailEntry, PhoneEntry, clean


def validate_broker_contact(record: dict) -> ContactSummary:
    """Convert the Host-sanitized contract without deriving a new identity."""
    if not isinstance(record, dict):
        raise ValueError("Broker contact must be an object.")
    allowed = {
        "contact_reference", "display_name", "given_name", "family_name",
        "organization", "emails", "phones",
    }
    if set(record) != allowed or not REF.fullmatch(record["contact_reference"]):
        raise ValueError("Broker contact identity or fields are invalid.")

    def bounded_text(value, limit):
        if not isinstance(value, str) or len(value) > limit:
            raise ValueError("Broker contact text is out of bounds.")
        return clean(value, limit)

    emails = []
    if not isinstance(record["emails"], list) or len(record["emails"]) > 10:
        raise ValueError("Broker email list is out of bounds.")
    for item in record["emails"]:
        if not isinstance(item, dict) or set(item) != {"label", "address"}:
            raise ValueError("Broker email is invalid.")
        emails.append(EmailEntry(bounded_text(item["label"], 50), bounded_text(item["address"], 254)))

    phones = []
    if not isinstance(record["phones"], list) or len(record["phones"]) > 10:
        raise ValueError("Broker phone list is out of bounds.")
    for item in record["phones"]:
        if not isinstance(item, dict) or set(item) != {"label", "number", "normalized_number"}:
            raise ValueError("Broker phone is invalid.")
        phones.append(PhoneEntry(
            bounded_text(item["label"], 50),
            bounded_text(item["number"], 80),
            bounded_text(item["normalized_number"], 80),
        ))
    return ContactSummary(
        record["contact_reference"],
        bounded_text(record["display_name"], 200),
        bounded_text(record["given_name"], 200),
        bounded_text(record["family_name"], 200),
        bounded_text(record["organization"], 200),
        tuple(dict.fromkeys(emails)), tuple(dict.fromkeys(phones)),
    )


def sanitize(record: dict) -> ContactSummary:
    native_identifier = clean(record.get("identifier", ""), 80)
    if not native_identifier:
        raise ValueError("Native contact identifier is required.")
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

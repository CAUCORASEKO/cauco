"""Apple Contacts read connector metadata and explicit read service."""

import sys
from datetime import datetime

from cauco_core.connectors.models import (
    CapabilityDefinition,
    ConnectorAccessMode,
    ConnectorAvailability,
    ConnectorHealth,
    ConnectorIdentity,
    ConnectorPlatform,
    ConnectorRiskLevel,
)

from .models import ContactSearchResponse
from .native import ContactsGateway, PyObjCContactsGateway, create_default_contacts_gateway
from .permissions import CONTACTS_PERMISSION_ID, permission_definition
from .sanitizer import sanitize


class AppleContactsConnector:
    def __init__(self, gateway: ContactsGateway | None = None) -> None:
        self.gateway = gateway or create_default_contacts_gateway()
        self._metadata = ConnectorIdentity(
            "apple_contacts.local",
            "apple_contacts",
            "1.0",
            ConnectorAvailability.AVAILABLE
            if isinstance(self.gateway, PyObjCContactsGateway) and sys.platform == "darwin"
            else ConnectorAvailability.UNAVAILABLE,
            ConnectorHealth.UNKNOWN,
            ConnectorPlatform.MACOS,
            True,
            application_bundle_id="com.apple.AddressBook",
            name_message_key="apple_contacts.name",
            description_message_key="apple_contacts.description",
            capability_ids=("contacts.search", "contacts.get", "contacts.list_limited"),
            limitations=("Read-only, bounded access; no contact data is read at startup.",),
        )

    @property
    def metadata(self):
        return self._metadata

    def capabilities(self):
        return tuple(
            CapabilityDefinition(
                item,
                "contacts",
                item.split(".")[1],
                "personal_data_read",
                ConnectorAccessMode.READ,
                ConnectorRiskLevel.MODERATE,
                exposes_personal_data=True,
                required_permission_ids=(CONTACTS_PERMISSION_ID,),
                name_message_key=f"{item}.name",
                description_message_key=f"{item}.description",
            )
            for item in self.metadata.capability_ids
        )

    def permissions(self):
        return (permission_definition(self.gateway.authorization_state()),)

    def request_permission(self):
        return self.gateway.request_permission()

    def search(self, query, now: datetime) -> ContactSearchResponse:
        records = self.gateway.search(
            query,
            ("identifier", "given_name", "family_name", "organization", "emails", "phones"),
            query.limit + 1,
        )
        results = tuple(sanitize(record) for record in records[: query.limit])
        return ContactSearchResponse(query, results, len(results), len(records) > query.limit, now)

    def get(self, reference, now):
        record = self.gateway.get(
            reference,
            ("identifier", "given_name", "family_name", "organization", "emails", "phones"),
        )
        if record is None:
            return None
        return sanitize(record)

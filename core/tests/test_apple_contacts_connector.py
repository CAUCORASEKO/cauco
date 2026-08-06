"""Tests for the injected, read-only Apple Contacts connector boundary."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from cauco_core.connectors.apple_contacts.connector import AppleContactsConnector
from cauco_core.connectors.apple_contacts.models import ContactQuery, ContactSummary
from cauco_core.connectors.apple_contacts.permissions import CONTACTS_PERMISSION_ID
from cauco_core.connectors.models import PermissionState


class FakeGateway:
    def __init__(self, state=PermissionState.GRANTED):
        self.state = state
        self.requested_keys = None
        self.reads = 0

    def authorization_state(self):
        return self.state

    def request_permission(self):
        self.state = PermissionState.GRANTED
        return self.state

    def search(self, query, keys, limit):
        self.requested_keys = keys
        self.reads += 1
        return [
            {
                "identifier": "native-opaque-id",
                "display_name": "Ándrés\x00 Doe",
                "given_name": "Ándrés",
                "family_name": "Doe",
                "emails": [
                    {"label": "work", "address": "a@example.test"},
                    {"label": "work", "address": "a@example.test"},
                ],
                "phones": [
                    {
                        "label": "mobile",
                        "number": "+358 1",
                    },
                    {"label": "mobile", "number": "+358 1"},
                ],
            }
        ]

    def get(self, reference, keys):
        return None


def test_contact_models_are_immutable_and_opaque():
    contact = ContactSummary("contact_opaque123", "Ándrés", emails=())
    with pytest.raises(FrozenInstanceError):
        contact.display_name = "other"  # type: ignore[misc]
    with pytest.raises(ValueError):
        ContactSummary("database-row-1", "Name")


def test_query_requires_bounded_explicit_field():
    with pytest.raises(ValueError):
        ContactQuery()
    with pytest.raises(ValueError):
        ContactQuery(name="x" * 201)


def test_metadata_declares_only_read_capabilities_and_permission():
    connector = AppleContactsConnector(FakeGateway())
    assert connector.metadata.connector_id == "apple_contacts.local"
    assert connector.metadata.provider_id == "apple_contacts"
    assert {item.capability_id for item in connector.capabilities()} == {
        "contacts.search",
        "contacts.get",
        "contacts.list_limited",
    }
    assert connector.permissions()[0].permission_id == CONTACTS_PERMISSION_ID


def test_permission_request_does_not_read_contacts():
    gateway = FakeGateway(PermissionState.NOT_REQUESTED)
    connector = AppleContactsConnector(gateway)
    assert connector.request_permission() == PermissionState.GRANTED
    assert gateway.reads == 0


def test_search_requests_only_allowlisted_keys_and_sanitizes():
    gateway = FakeGateway()
    result = AppleContactsConnector(gateway).search(ContactQuery(name="Ándrés"), datetime.now(UTC))
    assert gateway.requested_keys == (
        "identifier",
        "given_name",
        "family_name",
        "organization",
        "emails",
        "phones",
    )
    assert result.results[0].display_name == "Ándrés Doe"
    assert len(result.results[0].emails) == 1
    assert len(result.results[0].phones) == 1


def test_unavailable_permission_is_exposed_without_read():
    gateway = FakeGateway(PermissionState.DENIED)
    connector = AppleContactsConnector(gateway)
    assert connector.permissions()[0].state == PermissionState.DENIED
    assert gateway.reads == 0


def test_missing_contact_is_safe():
    assert AppleContactsConnector(FakeGateway()).get("contact_opaque123", datetime.now(UTC)) is None

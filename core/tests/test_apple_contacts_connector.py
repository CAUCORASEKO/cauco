"""Tests for the injected, read-only Apple Contacts connector boundary."""

import platform
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from cauco_core.connectors.apple_contacts.connector import AppleContactsConnector
from cauco_core.connectors.apple_contacts.exceptions import (
    ContactsPermissionRequestError,
    ContactsPermissionTimeoutError,
)
from cauco_core.connectors.apple_contacts.models import ContactQuery, ContactSummary
from cauco_core.connectors.apple_contacts.native import (
    BrokerContactsGateway,
    PyObjCContactsGateway,
    UnavailableContactsGateway,
    create_default_contacts_gateway,
)
from cauco_core.connectors.apple_contacts.sanitizer import sanitize, validate_broker_contact
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


class NoAuthorizationGateway(FakeGateway):
    def authorization_state(self):
        raise AssertionError("startup must not inspect authorization")


class FakeBroker:
    configured = True

    def __init__(self, state="granted"):
        self.state = state
        self.status_reads = 0
        self.search_reads = 0
        self.payload = {
            "contact_reference": "contact_hostref01",
            "display_name": "Ada Lovelace",
            "given_name": "Ada",
            "family_name": "Lovelace",
            "organization": "Analytical Engines",
            "emails": [{"label": "work", "address": "ada@example.test"}],
            "phones": [{"label": "mobile", "number": "+1 2", "normalized_number": "+12"}],
        }

    def contacts_status(self):
        self.status_reads += 1
        return {"outcome": "success", "result": {"state": self.state}}

    def contacts_search(self, query, limit):
        self.search_reads += 1
        return {"outcome": "success", "result": {"results": [self.payload], "result_count": 1, "truncated": False}}


def test_broker_reference_survives_without_legacy_hashing():
    broker = FakeBroker()
    result = AppleContactsConnector(broker_client=broker).search(
        ContactQuery(name="Ada"), datetime.now(UTC)
    )
    assert result.results[0].contact_reference == "contact_hostref01"
    assert result.results[0].contact_reference != "contact_e3b0c44298fc1c149afbf4c8"
    assert result.results[0].phones[0].normalized_number == "+12"


@pytest.mark.parametrize("reference", [None, "", "contact_e3b0c44298fc1c149afbf4c8!", "native-id"])
def test_broker_missing_or_malformed_reference_fails_closed(reference):
    broker = FakeBroker()
    if reference is None:
        broker.payload.pop("contact_reference")
    else:
        broker.payload["contact_reference"] = reference
    connector = AppleContactsConnector(broker_client=broker)
    assert connector.search(ContactQuery(name="Ada"), datetime.now(UTC)).results == ()


def test_broker_native_identifier_is_rejected_and_legacy_identity_stays_separate():
    broker = FakeBroker()
    broker.payload["identifier"] = "native-secret"
    assert AppleContactsConnector(broker_client=broker).search(
        ContactQuery(name="Ada"), datetime.now(UTC)
    ).results == ()
    assert sanitize({"identifier": "native-secret", "display_name": "Ada"}).contact_reference != "contact_e3b0c44298fc1c149afbf4c8"
    with pytest.raises(ValueError):
        sanitize({"display_name": "missing identity"})


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("granted", PermissionState.GRANTED),
        ("notRequested", PermissionState.NOT_REQUESTED),
        ("denied", PermissionState.DENIED),
        ("restricted", PermissionState.RESTRICTED),
        ("unavailable", PermissionState.UNAVAILABLE),
    ],
)
def test_configured_broker_is_authoritative_for_permission(state, expected):
    broker = FakeBroker(state)
    connector = AppleContactsConnector(FakeGateway(PermissionState.DENIED), broker_client=broker)
    assert connector.permissions()[0].state == expected
    assert broker.status_reads == 1


def test_malformed_broker_permission_fails_closed_without_fallback():
    class MalformedBroker(FakeBroker):
        def contacts_status(self):
            self.status_reads += 1
            return {"outcome": "success", "result": {"unexpected": True}}

    broker = MalformedBroker()
    connector = AppleContactsConnector(FakeGateway(PermissionState.GRANTED), broker_client=broker)
    assert connector.permissions()[0].state == PermissionState.UNAVAILABLE


def test_broker_transport_failure_fails_closed_without_pyobjc_fallback():
    class FailedBroker(FakeBroker):
        def contacts_status(self):
            raise RuntimeError("transport failure")

    connector = AppleContactsConnector(FakeGateway(PermissionState.GRANTED), broker_client=FailedBroker())
    assert connector.permissions()[0].state == PermissionState.UNAVAILABLE


def test_absent_broker_preserves_injected_gateway_and_permission_check_is_read_free():
    gateway = FakeGateway(PermissionState.GRANTED)
    connector = AppleContactsConnector(gateway, broker_client=None)
    assert connector.permissions()[0].state == PermissionState.GRANTED
    assert gateway.reads == 0


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


def test_connector_construction_does_not_inspect_authorization():
    connector = AppleContactsConnector(NoAuthorizationGateway())
    assert connector.metadata.connector_id == "apple_contacts.local"


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


def test_non_macos_factory_is_unavailable():
    gateway = create_default_contacts_gateway()
    if platform.system() == "Darwin":
        assert isinstance(gateway, PyObjCContactsGateway)
    else:
        assert isinstance(gateway, UnavailableContactsGateway)


def test_authorization_mapping_with_fake_contacts_module():
    class Store:
        def authorizationStatusForEntityType_(self, entity_type):
            return 3

    class Module:
        CNEntityTypeContacts = 0
        CNAuthorizationStatusNotDetermined = 0
        CNAuthorizationStatusRestricted = 1
        CNAuthorizationStatusDenied = 2
        CNAuthorizationStatusAuthorized = 3

        class CNContactStore:
            @classmethod
            def alloc(cls):
                return cls()

            def init(self):
                return Store()

            @classmethod
            def authorizationStatusForEntityType_(cls, entity_type):
                return 3

    assert PyObjCContactsGateway(Module()).authorization_state() == PermissionState.GRANTED


def test_authorization_uses_store_class_method_not_instance_method():
    class Store:
        def authorizationStatusForEntityType_(self, entity_type):
            raise AssertionError("instance authorization method must not be used")

    class Module:
        CNEntityTypeContacts = 0
        CNAuthorizationStatusNotDetermined = 0
        CNAuthorizationStatusRestricted = 1
        CNAuthorizationStatusDenied = 2
        CNAuthorizationStatusAuthorized = 3

        class CNContactStore:
            @classmethod
            def alloc(cls):
                return cls()

            def init(self):
                return Store()

            @classmethod
            def authorizationStatusForEntityType_(cls, entity_type):
                return 3

    assert PyObjCContactsGateway(Module()).authorization_state() == PermissionState.GRANTED


def test_permission_request_timeout_is_safe():
    class Store:
        def requestAccessForEntityType_completionHandler_(self, entity_type, completion):
            return None

    class Module:
        CNEntityTypeContacts = 0
        CNAuthorizationStatusNotDetermined = 0
        CNAuthorizationStatusRestricted = 1
        CNAuthorizationStatusDenied = 2
        CNAuthorizationStatusAuthorized = 3

        class CNContactStore:
            @classmethod
            def alloc(cls):
                return cls()

            def init(self):
                return Store()

    with pytest.raises(ContactsPermissionTimeoutError):
        PyObjCContactsGateway(Module(), timeout=0.001).request_permission()


@pytest.mark.parametrize(
    "granted, expected", [(True, PermissionState.GRANTED), (False, PermissionState.DENIED)]
)
def test_permission_request_uses_completion_handler_once(granted, expected):
    calls = []

    class Store:
        def requestAccessForEntityType_completionHandler_(self, entity_type, completion):
            calls.append("request")
            completion(granted, None)

    class Module:
        CNEntityTypeContacts = 0
        CNAuthorizationStatusNotDetermined = 0
        CNAuthorizationStatusRestricted = 1
        CNAuthorizationStatusDenied = 2
        CNAuthorizationStatusAuthorized = 3

        class CNContactStore:
            @classmethod
            def alloc(cls):
                return cls()

            def init(self):
                return Store()

    assert PyObjCContactsGateway(Module()).request_permission() == expected
    assert calls == ["request"]


def test_permission_request_native_error_is_safe():
    class Store:
        def requestAccessForEntityType_completionHandler_(self, entity_type, completion):
            completion(False, object())

    class Module:
        CNEntityTypeContacts = 0
        CNAuthorizationStatusNotDetermined = 0
        CNAuthorizationStatusRestricted = 1
        CNAuthorizationStatusDenied = 2
        CNAuthorizationStatusAuthorized = 3

        class CNContactStore:
            @classmethod
            def alloc(cls):
                return cls()

            def init(self):
                return Store()

    with pytest.raises(ContactsPermissionRequestError) as error:
        PyObjCContactsGateway(Module()).request_permission()
    assert "native" not in str(error.value).lower()

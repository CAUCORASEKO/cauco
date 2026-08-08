"""Optional native gateway boundary; no subprocess or database fallback."""

from __future__ import annotations

import base64
import platform
import threading
from typing import Protocol

from cauco_core.connectors.models import PermissionState

from .exceptions import ContactsPermissionRequestError, ContactsPermissionTimeoutError
from cauco_core.native_broker import NativeBrokerClient, NativeBrokerUnavailable


class ContactsGateway(Protocol):
    def authorization_state(self) -> PermissionState: ...
    def request_permission(self) -> PermissionState: ...
    def search(self, query, keys: tuple[str, ...], limit: int): ...
    def get(self, reference: str, keys: tuple[str, ...]): ...

class BrokerContactsGateway:
    """Production gateway whose permission authority is the authenticated Host."""
    def __init__(self, client: NativeBrokerClient):
        self.client = client

    def authorization_state(self) -> PermissionState:
        try:
            response = self.client.contacts_status()
            result = response.get("result")
            state = result.get("state") if isinstance(result, dict) else None
            states = {
                "granted": PermissionState.GRANTED,
                "notRequested": PermissionState.NOT_REQUESTED,
                "denied": PermissionState.DENIED,
                "restricted": PermissionState.RESTRICTED,
                "unavailable": PermissionState.UNAVAILABLE,
            }
            return states.get(state, PermissionState.UNAVAILABLE)
        except (NativeBrokerUnavailable, AttributeError, TypeError, ValueError, RuntimeError):
            return PermissionState.UNAVAILABLE

    def request_permission(self):
        return self.authorization_state()

    def search(self, query, keys, limit):
        response = self.client.contacts_search(
            query.name or query.organization or query.email or query.phone, min(limit, 20)
        )
        return response["result"]["results"]

    def get(self, reference, keys):
        response = self.client.contacts_get(reference)
        return response["result"]

    def list_limited(self, limit):
        return self.client.contacts_list_limited(limit)["result"]["results"]


class UnavailableContactsGateway:
    def authorization_state(self) -> PermissionState:
        if platform.system() != "Darwin":
            return PermissionState.UNAVAILABLE
        return PermissionState.UNAVAILABLE

    def request_permission(self) -> PermissionState:
        return self.authorization_state()

    def search(self, query, keys, limit):
        return ()

    def get(self, reference, keys):
        return None


class PyObjCContactsGateway:
    """Synchronous, bounded wrapper around CNContactStore."""

    def __init__(self, contacts_module=None, timeout: float = 15.0) -> None:
        if contacts_module is None:
            import Contacts as contacts_module
        self.contacts = contacts_module
        self.timeout = timeout
        self.store = contacts_module.CNContactStore.alloc().init()
        self._lock = threading.RLock()

    def authorization_state(self) -> PermissionState:
        status = self.contacts.CNContactStore.authorizationStatusForEntityType_(
            self.contacts.CNEntityTypeContacts
        )
        states = {
            self.contacts.CNAuthorizationStatusNotDetermined: PermissionState.NOT_REQUESTED,
            self.contacts.CNAuthorizationStatusRestricted: PermissionState.RESTRICTED,
            self.contacts.CNAuthorizationStatusDenied: PermissionState.DENIED,
            self.contacts.CNAuthorizationStatusAuthorized: PermissionState.GRANTED,
        }
        return states.get(status, PermissionState.UNKNOWN)

    def request_permission(self) -> PermissionState:
        event = threading.Event()
        result = {"state": PermissionState.UNKNOWN, "error": False}

        def completion(granted, error):
            result["state"] = PermissionState.GRANTED if granted else PermissionState.DENIED
            result["error"] = error is not None
            event.set()

        try:
            self.store.requestAccessForEntityType_completionHandler_(
                self.contacts.CNEntityTypeContacts, completion
            )
        except (AttributeError, OSError, RuntimeError, TypeError) as error:
            raise ContactsPermissionRequestError(
                "Contacts permission request was unavailable."
            ) from error
        if not event.wait(self.timeout):
            raise ContactsPermissionTimeoutError("Contacts permission request timed out.")
        if result["error"]:
            raise ContactsPermissionRequestError("Contacts permission request failed.")
        return result["state"]

    def search(self, query, keys: tuple[str, ...], limit: int):
        if self.authorization_state() != PermissionState.GRANTED:
            return ()
        request = self.contacts.CNFetchRequest.alloc().initWithKeysToFetch_(self._native_keys(keys))
        if query.name:
            request.setPredicate_(
                self.contacts.CNContact.predicateForContactsMatchingName_(query.name)
            )
        records = []
        self._enumerate(request, records, limit)
        return tuple(self._record(contact) for contact in records)

    def get(self, reference: str, keys: tuple[str, ...]):
        if self.authorization_state() != PermissionState.GRANTED:
            return None
        try:
            native_id = base64.urlsafe_b64decode(
                reference.removeprefix("contact_") + "==="
            ).decode()
        except (ValueError, UnicodeDecodeError):
            return None
        request = self.contacts.CNFetchRequest.alloc().initWithKeysToFetch_(self._native_keys(keys))
        request.setPredicate_(
            self.contacts.CNContact.predicateForContactsWithIdentifiers_([native_id])
        )
        records = []
        self._enumerate(request, records, 1)
        return self._record(records[0]) if records else None

    def _enumerate(self, request, records: list, limit: int) -> None:
        def block(contact, stop):
            records.append(contact)
            if len(records) >= limit:
                stop[0] = True

        self.store.enumerateContactsWithFetchRequest_error_usingBlock_(request, None, block)

    def _record(self, contact) -> dict:
        native_id = str(contact.identifier)
        reference = "contact_" + base64.urlsafe_b64encode(native_id.encode()).decode().rstrip("=")
        return {
            "identifier": reference,
            "display_name": " ".join(
                part for part in (contact.givenName, contact.middleName, contact.familyName) if part
            ),
            "given_name": contact.givenName,
            "middle_name": contact.middleName,
            "family_name": contact.familyName,
            "organization": contact.organizationName,
            "emails": [
                {"label": item.label or "", "address": item.value or ""}
                for item in contact.emailAddresses
            ],
            "phones": [
                {"label": item.label or "", "number": item.value.stringValue() or ""}
                for item in contact.phoneNumbers
            ],
        }

    @staticmethod
    def _native_keys(keys: tuple[str, ...]):
        names = {
            "identifier": "identifier",
            "given_name": "givenName",
            "middle_name": "middleName",
            "family_name": "familyName",
            "organization": "organizationName",
            "emails": "emailAddresses",
            "phones": "phoneNumbers",
        }
        return [names[key] for key in keys if key in names]


def create_default_contacts_gateway():
    if platform.system() != "Darwin":
        return UnavailableContactsGateway()
    try:
        return PyObjCContactsGateway()
    except (ImportError, OSError, RuntimeError, TypeError):
        return UnavailableContactsGateway()

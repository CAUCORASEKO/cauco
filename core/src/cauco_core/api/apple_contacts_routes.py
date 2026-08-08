"""Explicit, bounded Apple Contacts read API."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from cauco_core.connectors.apple_contacts.exceptions import ContactsNativeError
from cauco_core.connectors.apple_contacts.models import ContactQuery
from cauco_core.native_broker import NativeBrokerUnavailable
from cauco_core.connectors.models import ConnectorRequest, PermissionState

router = APIRouter(prefix="/api/apple-contacts", tags=["apple-contacts"])


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, max_length=200)
    organization: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=20, ge=1, le=50)
    request_id: str = Field(min_length=1, max_length=100)
    requester_id: str = Field(min_length=1, max_length=100)
    request_locale: str = "en"
    response_locale: str = "en"
    interface_locale: str = "en"
    explicit_user_request: bool = False


def _contact(value: Any) -> dict[str, Any]:
    return {field: getattr(value, field) for field in value.__dataclass_fields__}


@router.get("/status")
def connector_status(request: Request) -> dict[str, Any]:
    connector = request.app.state.apple_contacts_connector
    try:
        permission_state = connector.permissions()[0].state
    except (OSError, RuntimeError, TypeError):
        permission_state = PermissionState.UNKNOWN
    return {
        "connector": connector.metadata.connector_id,
        "provider": connector.metadata.provider_id,
        "registered": True,
        "availability": connector.metadata.availability.value,
        "permission_state": permission_state.value,
        "capabilities": list(connector.metadata.capability_ids),
        "method": "apple-contacts-read-v1",
        "limitations": list(connector.metadata.limitations),
    }


@router.post("/permissions/request")
def request_permission(request: Request) -> dict[str, Any]:
    connector = request.app.state.apple_contacts_connector
    try:
        state = connector.request_permission()
    except ContactsNativeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Contacts permission request is unavailable.",
        ) from error
    return {
        "permission_id": "macos.contacts.read",
        "state": state.value,
        "method": "apple-contacts-read-v1",
        "limitations": [
            "Permission is requested only by this explicit endpoint; no contacts are read."
        ],
    }


@router.post("/search")
def search_contacts(payload: SearchRequest, request: Request) -> dict[str, Any]:
    try:
        query = ContactQuery(
            payload.name, payload.organization, payload.email, payload.phone, payload.limit
        )
        runtime_request = ConnectorRequest(
            payload.request_id,
            "contacts.search",
            None,
            payload.requester_id,
            payload.request_locale,
            payload.response_locale,
            payload.interface_locale,
            explicit_user_request=payload.explicit_user_request,
            created_at=datetime.now().astimezone(),
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid contact search request.",
        ) from error
    routing = request.app.state.connector_runtime.resolve(runtime_request)
    if not routing.executable:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Contacts search is not eligible."
        )
    try:
        response = request.app.state.apple_contacts_connector.search(query, datetime.now().astimezone())
    except NativeBrokerUnavailable as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Contacts search is unavailable.") from error
    return {
        "query": {
            field: getattr(response.query, field) for field in response.query.__dataclass_fields__
        },
        "results": [_contact(item) for item in response.results],
        "result_count": response.result_count,
        "truncated": response.truncated,
        "executed_at": response.executed_at,
        "connector_id": response.connector_id,
        "provider_id": response.provider_id,
        "method": response.method,
        "limitations": list(response.limitations),
    }


@router.get("/contacts")
def list_contacts(
    request: Request,
    limit: int = Query(20, ge=1, le=20),
    request_id: str = Query(..., min_length=1, max_length=100),
    requester_id: str = Query(..., min_length=1, max_length=100),
    explicit_user_request: bool = True,
) -> dict[str, Any]:
    runtime_request = ConnectorRequest(
        request_id, "contacts.list_limited", None, requester_id, "en", "en", "en",
        explicit_user_request=explicit_user_request, created_at=datetime.now().astimezone(),
    )
    if not request.app.state.connector_runtime.resolve(runtime_request).executable:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Contacts list is not eligible.")
    try:
        results = request.app.state.apple_contacts_connector.list_limited(limit)
    except NativeBrokerUnavailable as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Contacts list is unavailable.") from error
    return {"results": [_contact(item) for item in results], "result_count": len(results),
            "truncated": len(results) == limit, "method": "contacts.list_limited.v1"}


@router.get("/contacts/{contact_reference}")
def get_contact(
    contact_reference: str,
    request: Request,
    request_id: str = Query(..., min_length=1, max_length=100),
    requester_id: str = Query(..., min_length=1, max_length=100),
    explicit_user_request: bool = True,
    confirmation_request_id: str | None = None,
) -> dict[str, Any]:
    runtime_request = ConnectorRequest(
        request_id, "contacts.get", None, requester_id, "en", "en", "en",
        explicit_user_request=explicit_user_request,
        confirmation_request_id=confirmation_request_id,
        created_at=datetime.now().astimezone(),
    )
    routing = request.app.state.connector_runtime.resolve(runtime_request)
    if not routing.executable:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Contacts get is not eligible.")
    try:
        contact = request.app.state.apple_contacts_connector.get(
            contact_reference, datetime.now().astimezone()
        )
    except NativeBrokerUnavailable as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact reference is unavailable.") from error
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact reference is unavailable.")
    return {"contact": _contact(contact), "method": "apple-contacts-read-v1", "limitations": list(contact.limitations)}

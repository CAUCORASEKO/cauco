"""Explicit, bounded Apple Contacts read API."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
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

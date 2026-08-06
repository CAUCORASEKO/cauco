"""Read-only connector inspection and routing endpoints."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from cauco_core.connectors.exceptions import ConnectorNotFoundError
from cauco_core.connectors.models import ConnectorRequest

router = APIRouter(prefix="/api/connectors", tags=["connectors"])


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResolveRequest(StrictModel):
    request_id: str = Field(min_length=1, max_length=100)
    capability_id: str = Field(min_length=1, max_length=100)
    preferred_connector_id: str | None = Field(default=None, max_length=100)
    requester_id: str = Field(min_length=1, max_length=100)
    request_locale: str = Field(default="en", max_length=20)
    response_locale: str = Field(default="en", max_length=20)
    interface_locale: str = Field(default="en", max_length=20)
    fallback_locale: str = Field(default="en", max_length=20)
    arguments: dict[str, Any] = Field(default_factory=dict, max_length=100)
    explicit_user_request: bool = False
    confirmation_request_id: str | None = Field(default=None, max_length=100)


class ConnectorListResponse(StrictModel):
    connectors: list[dict[str, Any]]
    count: int
    method: str
    limitations: list[str]


def _identity(metadata: Any) -> dict[str, Any]:
    return {
        "connector_id": metadata.connector_id,
        "provider_id": metadata.provider_id,
        "version": metadata.version,
        "availability": metadata.availability.value,
        "health": metadata.health.value,
        "platform": metadata.platform.value,
        "local": metadata.local,
        "priority": metadata.priority,
        "application_bundle_id": metadata.application_bundle_id,
        "name_message_key": metadata.name_message_key,
        "description_message_key": metadata.description_message_key,
        "capability_ids": list(metadata.capability_ids),
        "limitations": list(metadata.limitations),
        "diagnostics": dict(metadata.diagnostics),
    }


@router.get("", response_model=ConnectorListResponse)
def list_connectors(request: Request) -> ConnectorListResponse:
    connectors = [_identity(item) for item in request.app.state.connector_registry.list()]
    return ConnectorListResponse(
        connectors=connectors,
        count=len(connectors),
        method="connector-routing-v1",
        limitations=["Metadata inspection only; no operating-system action is performed."],
    )


@router.get("/capabilities")
def list_capabilities(
    request: Request,
    connector_id: str | None = Query(default=None, max_length=100),
    domain: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=100, ge=1, le=100),
) -> dict[str, Any]:
    capabilities = request.app.state.connector_registry.capabilities(limit=100)
    if domain is not None:
        capabilities = tuple(item for item in capabilities if item.domain == domain)
    if connector_id is not None:
        metadata = request.app.state.connector_registry.get_metadata(connector_id)
        capabilities = tuple(
            item for item in capabilities if item.capability_id in metadata.capability_ids
        )
    capabilities = capabilities[:limit]
    return {
        "capabilities": [
            {
                "capability_id": item.capability_id,
                "domain": item.domain,
                "action": item.action,
                "semantic_category": item.semantic_category,
                "access_mode": item.access_mode.value,
                "risk_level": item.risk_level.value,
                "confirmation_required": item.confirmation_required,
                "mutates_external_state": item.mutates_external_state,
                "exposes_personal_data": item.exposes_personal_data,
                "required_permission_ids": list(item.required_permission_ids),
                "name_message_key": item.name_message_key,
                "description_message_key": item.description_message_key,
                "limitations": list(item.limitations),
            }
            for item in capabilities
        ],
        "count": len(capabilities),
        "method": "connector-routing-v1",
        "limitations": ["Metadata inspection only; no connector action is performed."],
    }


@router.get("/{connector_id}")
def get_connector(connector_id: str, request: Request) -> dict[str, Any]:
    try:
        connector = request.app.state.connector_registry._get_connector(connector_id)
    except ConnectorNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found."
        ) from error
    return {
        "connector": _identity(connector.metadata),
        "capabilities": [item.capability_id for item in connector.capabilities()],
        "count": 1,
        "method": "connector-routing-v1",
        "limitations": ["Metadata inspection only; no connector action is performed."],
    }


@router.post("/resolve")
def resolve_connector(payload: ResolveRequest, request: Request) -> dict[str, Any]:
    runtime_request = ConnectorRequest(
        **payload.model_dump(),
        created_at=datetime.now().astimezone(),
    )
    result = request.app.state.connector_runtime.resolve(runtime_request)
    return {
        "request_id": result.request_id,
        "capability_id": result.capability_id,
        "selected_connector_id": result.selected_connector_id,
        "eligible_connector_ids": list(result.eligible_connector_ids),
        "rejected_connector_reason_codes": dict(result.rejected_connector_reason_codes),
        "confirmation_required": result.confirmation_required,
        "executable": result.executable,
        "limitations": list(result.limitations),
        "method": result.method,
    }

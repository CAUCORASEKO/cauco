from enum import Enum
from types import MappingProxyType
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from cauco_core.api.execution_routes import record_response
from cauco_core.memory_writing.store import ProposalStoreError
from cauco_core.mutations.models import (
    MutationCapacityError,
    MutationConflictError,
    MutationForbiddenError,
    MutationNotFoundError,
    MutationPreview,
    MutationValidationError,
)

router = APIRouter(prefix="/api/executions", tags=["mutations"])


class MutationApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MutationConfirmationRequest(MutationApiModel):
    preview_id: str = Field(min_length=20, max_length=100)
    preview_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmation_phrase: str = Field(min_length=1, max_length=100)


@router.post(
    "/{execution_id}/steps/{step_index}/mutation-preview",
    status_code=status.HTTP_201_CREATED,
)
def create_mutation_preview(execution_id: str, step_index: int, request: Request) -> dict[str, Any]:
    try:
        return preview_response(
            request.app.state.mutation_service.create_preview(execution_id, step_index)
        )
    except Exception as error:
        raise_http(error)


@router.get("/{execution_id}/steps/{step_index}/mutation-preview")
def get_mutation_preview(execution_id: str, step_index: int, request: Request) -> dict[str, Any]:
    try:
        return preview_response(
            request.app.state.mutation_service.get_preview(execution_id, step_index)
        )
    except Exception as error:
        raise_http(error)


@router.post("/{execution_id}/steps/{step_index}/confirm-mutation")
def confirm_mutation(
    execution_id: str,
    step_index: int,
    payload: MutationConfirmationRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        return record_response(
            request.app.state.mutation_service.confirm(
                execution_id,
                step_index,
                preview_id=payload.preview_id,
                preview_digest_value=payload.preview_digest,
                confirmation_phrase=payload.confirmation_phrase,
            )
        )
    except Exception as error:
        raise_http(error)


@router.post("/{execution_id}/steps/{step_index}/cancel-mutation-preview")
def cancel_mutation_preview(execution_id: str, step_index: int, request: Request) -> dict[str, Any]:
    try:
        return preview_response(
            request.app.state.mutation_service.cancel_preview(execution_id, step_index)
        )
    except Exception as error:
        raise_http(error)


def preview_response(preview: MutationPreview) -> dict[str, Any]:
    return {
        "preview_id": preview.preview_id,
        "execution_id": preview.execution_id,
        "review_id": preview.review_id,
        "step_index": preview.step_index,
        "tool_id": preview.tool_id,
        "operation_id": preview.operation_id,
        "target": preview.target,
        "normalized_arguments": thaw(preview.normalized_arguments),
        "before_state": thaw(preview.before_state),
        "proposed_after_state": thaw(preview.proposed_after_state),
        "diff_preview": preview.diff_preview,
        "preview_digest": preview.preview_digest,
        "confirmation_phrase": preview.confirmation_phrase,
        "created_at": preview.created_at.isoformat(),
        "expires_at": preview.expires_at.isoformat(),
        "status": preview.status.value,
        "warning": preview.warning,
    }


def thaw(value: Any) -> Any:
    if isinstance(value, (dict, MappingProxyType)):
        return {key: thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    return value


def raise_http(error: Exception) -> None:
    if isinstance(error, MutationNotFoundError):
        raise HTTPException(status_code=404, detail=str(error)) from error
    if isinstance(error, MutationForbiddenError):
        raise HTTPException(status_code=403, detail=str(error)) from error
    if isinstance(error, MutationValidationError):
        raise HTTPException(status_code=422, detail=str(error)) from error
    if isinstance(error, (MutationConflictError, MutationCapacityError, ProposalStoreError)):
        raise HTTPException(status_code=409, detail=str(error)) from error
    raise error

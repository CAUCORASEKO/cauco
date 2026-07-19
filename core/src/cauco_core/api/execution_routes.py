from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from cauco_core.agents.review_store import (
    PlanReviewIntegrityError,
    PlanReviewNotFoundError,
)
from cauco_core.execution.models import (
    AgentPlanExecutionRecord,
    ExecutionCapacityError,
    ExecutionConflictError,
    ExecutionForbiddenError,
    ExecutionNotFoundError,
    ExecutionStatus,
    ExecutionValidationError,
)

router = APIRouter(prefix="/api/executions", tags=["executions"])


class ExecutionApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateExecutionRequest(ExecutionApiModel):
    review_id: str = Field(min_length=1, max_length=100)


class ExecuteStepRequest(ExecutionApiModel):
    timeout_seconds: float = Field(default=5.0, ge=0.1, le=30)
    max_output_chars: int = Field(default=20_000, ge=100, le=100_000)
    max_chars: int | None = Field(default=None, ge=1, le=100_000)
    max_entries: int | None = Field(default=None, ge=1, le=1000)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_execution(payload: CreateExecutionRequest, request: Request) -> dict[str, Any]:
    try:
        return record_response(request.app.state.execution_service.create(payload.review_id))
    except PlanReviewNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except (PlanReviewIntegrityError, ExecutionConflictError, ExecutionCapacityError) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.get("")
def list_executions(
    request: Request,
    execution_status: Annotated[ExecutionStatus | None, Query(alias="status")] = None,
    review_id: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict[str, Any]:
    records = request.app.state.execution_store.list(
        status=execution_status, review_id=review_id, limit=limit
    )
    return {"executions": [record_response(item) for item in records], "count": len(records)}


@router.get("/{execution_id}")
def get_execution(execution_id: str, request: Request) -> dict[str, Any]:
    try:
        return record_response(request.app.state.execution_store.get(execution_id))
    except ExecutionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.post("/{execution_id}/steps/{step_index}/execute")
def execute_step(
    execution_id: str,
    step_index: int,
    payload: ExecuteStepRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        record = request.app.state.execution_service.execute_step(
            execution_id,
            step_index,
            timeout_seconds=payload.timeout_seconds,
            max_output_chars=payload.max_output_chars,
            max_chars=payload.max_chars,
            max_entries=payload.max_entries,
        )
        return record_response(record)
    except (ExecutionNotFoundError, PlanReviewNotFoundError) as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except (ExecutionConflictError, PlanReviewIntegrityError) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except ExecutionForbiddenError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except ExecutionValidationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error


@router.post("/{execution_id}/cancel")
def cancel_execution(execution_id: str, request: Request) -> dict[str, Any]:
    try:
        return record_response(request.app.state.execution_service.cancel(execution_id))
    except ExecutionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ExecutionConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


def record_response(record: AgentPlanExecutionRecord) -> dict[str, Any]:
    return {
        "execution_id": record.execution_id,
        "review_id": record.review_id,
        "snapshot_digest": record.snapshot_digest,
        "status": record.status.value,
        "created_at": record.created_at.isoformat(),
        "started_at": _timestamp(record.started_at),
        "completed_at": _timestamp(record.completed_at),
        "current_step_index": record.current_step_index,
        "total_steps": record.total_steps,
        "step_records": [
            {
                "step_index": step.step_index,
                "tool_id": step.tool_id,
                "operation_id": step.operation_id,
                "target": step.target,
                "status": step.status.value,
                "started_at": _timestamp(step.started_at),
                "completed_at": _timestamp(step.completed_at),
                "result": (
                    {
                        "tool_id": step.result.tool_id,
                        "operation_id": step.result.operation_id,
                        "success": step.result.success,
                        "started_at": step.result.started_at.isoformat(),
                        "completed_at": step.result.completed_at.isoformat(),
                        "duration_ms": step.result.duration_ms,
                        "output": step.result.output,
                        "structured_data": thaw(step.result.structured_data),
                        "error_code": step.result.error_code,
                        "error_message": step.result.error_message,
                        "truncated": step.result.truncated,
                        "execution_performed": step.result.execution_performed,
                    }
                    if step.result is not None
                    else None
                ),
                "error": step.error,
                "execution_performed": step.execution_performed,
            }
            for step in record.step_records
        ],
        "execution_performed": record.execution_performed,
        "failure_reason": record.failure_reason,
        "audit_events": [
            {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "timestamp": event.timestamp.isoformat(),
                "execution_id": event.execution_id,
                "review_id": event.review_id,
                "step_index": event.step_index,
                "tool_id": event.tool_id,
                "operation_id": event.operation_id,
                "outcome": event.outcome,
                "safe_message": event.safe_message,
                "metadata": dict(event.metadata),
            }
            for event in record.audit_events
        ],
        "warning": record.warning,
    }


def thaw(value: Any) -> Any:
    if isinstance(value, (dict, MappingProxyType)):
        return {key: thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    return value


def _timestamp(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None

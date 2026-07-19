from typing import TypeAlias

from cauco_tools import ToolCategory, ToolDefinition, ToolOperation, ToolValidationResult
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix="/api/tools", tags=["tools"])
JsonScalar: TypeAlias = str | int | float | bool | None


class ToolApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PermissionResponse(ToolApiModel):
    name: str
    description: str


class OperationResponse(ToolApiModel):
    id: str
    description: str
    safe: bool
    confirmation_required: bool
    enabled: bool
    execution_enabled: bool


class ToolResponse(ToolApiModel):
    id: str
    display_name: str
    description: str
    category: ToolCategory
    version: str
    enabled: bool
    operations: list[OperationResponse]
    permissions: list[PermissionResponse]
    requires_confirmation: bool
    execution_enabled: bool
    metadata: dict[str, JsonScalar]


class ToolListResponse(ToolApiModel):
    tools: list[ToolResponse]
    count: int


class CategoryListResponse(ToolApiModel):
    categories: list[ToolCategory]


class OperationListResponse(ToolApiModel):
    tool_id: str
    operations: list[OperationResponse]


class ValidateToolRequest(ToolApiModel):
    tool_id: str = Field(min_length=1, max_length=100)
    operation_id: str = Field(min_length=1, max_length=100)


class ValidationResponse(ToolApiModel):
    tool_id: str
    operation_id: str
    valid: bool
    tool_exists: bool
    operation_exists: bool
    tool_enabled: bool
    operation_enabled: bool
    safe: bool | None
    confirmation_required: bool | None
    execution_enabled: bool
    reason: str | None


@router.get("", response_model=ToolListResponse)
def list_tools(request: Request) -> ToolListResponse:
    tools = [tool_response(tool) for tool in request.app.state.tool_registry.list()]
    return ToolListResponse(tools=tools, count=len(tools))


@router.get("/categories", response_model=CategoryListResponse)
def list_categories(request: Request) -> CategoryListResponse:
    return CategoryListResponse(categories=list(request.app.state.tool_registry.categories()))


@router.post("/validate", response_model=ValidationResponse)
def validate_tool(payload: ValidateToolRequest, request: Request) -> ValidationResponse:
    return validation_response(
        request.app.state.tool_registry.validate(payload.tool_id, payload.operation_id)
    )


@router.get("/{tool_id}/operations", response_model=OperationListResponse)
def list_operations(tool_id: str, request: Request) -> OperationListResponse:
    try:
        operations = request.app.state.tool_registry.operations(tool_id)
    except KeyError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return OperationListResponse(
        tool_id=tool_id,
        operations=[operation_response(operation) for operation in operations],
    )


@router.get("/{tool_id}", response_model=ToolResponse)
def get_tool(tool_id: str, request: Request) -> ToolResponse:
    try:
        return tool_response(request.app.state.tool_registry.get(tool_id))
    except KeyError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


def operation_response(operation: ToolOperation) -> OperationResponse:
    return OperationResponse(
        **{
            "id": operation.id,
            "description": operation.description,
            "safe": operation.safe,
            "confirmation_required": operation.confirmation_required,
            "enabled": operation.enabled,
            "execution_enabled": operation.execution_enabled,
        }
    )


def tool_response(tool: ToolDefinition) -> ToolResponse:
    return ToolResponse(
        id=tool.id,
        display_name=tool.display_name,
        description=tool.description,
        category=tool.category,
        version=tool.version,
        enabled=tool.enabled,
        operations=[operation_response(operation) for operation in tool.operations],
        permissions=[
            PermissionResponse(name=item.name, description=item.description)
            for item in tool.permissions
        ],
        requires_confirmation=tool.requires_confirmation,
        execution_enabled=tool.execution_enabled,
        metadata=dict(tool.metadata),
    )


def validation_response(result: ToolValidationResult) -> ValidationResponse:
    return ValidationResponse(
        **{field: getattr(result, field) for field in result.__dataclass_fields__}
    )

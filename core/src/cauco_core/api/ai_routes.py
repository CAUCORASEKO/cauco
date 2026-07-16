from typing import Annotated

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from cauco_core.ai.base import validate_model_name
from cauco_core.ai.exceptions import (
    MalformedProviderResponseError,
    ModelNotFoundError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from cauco_core.ai.service import AIService

router = APIRouter(prefix="/api/ai", tags=["ai"])
MessageText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8000)
]


class AIStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str
    available: bool
    base_url: str
    default_model: str
    default_model_installed: bool
    models_count: int = Field(ge=0)


class AIModelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    size: int = Field(ge=0)
    parameter_size: str | None = None
    quantization_level: str | None = None


class AIModelsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str
    models: list[AIModelResponse]


class AIChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: MessageText
    model: str | None = None

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_model_name(value)


class AIChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str
    model: str
    response: str
    used_memory: bool = False
    used_tools: list[str] = Field(default_factory=list)
    used_agents: list[str] = Field(default_factory=list)


def ai_service(request: Request) -> AIService:
    return request.app.state.ai_service


def provider_error(error: Exception) -> HTTPException:
    if isinstance(error, ModelNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    if isinstance(error, ProviderTimeoutError):
        return HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(error))
    if isinstance(error, MalformedProviderResponseError):
        return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error))
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error))


@router.get("/status", response_model=AIStatusResponse)
def get_ai_status(request: Request) -> AIStatusResponse:
    try:
        result = ai_service(request).status()
    except MalformedProviderResponseError as error:
        raise provider_error(error) from error
    return AIStatusResponse(
        provider=result.provider,
        available=result.available,
        base_url=result.base_url,
        default_model=result.default_model,
        default_model_installed=result.default_model_installed,
        models_count=result.models_count,
    )


@router.get("/models", response_model=AIModelsResponse)
def get_ai_models(request: Request) -> AIModelsResponse:
    service = ai_service(request)
    try:
        models = service.list_models()
    except (
        MalformedProviderResponseError,
        ModelNotFoundError,
        ProviderTimeoutError,
        ProviderUnavailableError,
    ) as error:
        raise provider_error(error) from error
    return AIModelsResponse(
        provider=service.provider.metadata.name,
        models=[
            AIModelResponse(
                name=model.name,
                size=model.size,
                parameter_size=model.parameter_size,
                quantization_level=model.quantization_level,
            )
            for model in models
        ],
    )


@router.post("/chat", response_model=AIChatResponse)
def post_ai_chat(payload: AIChatRequest, request: Request) -> AIChatResponse:
    try:
        result = ai_service(request).chat(payload.message, payload.model)
    except (
        MalformedProviderResponseError,
        ModelNotFoundError,
        ProviderTimeoutError,
        ProviderUnavailableError,
    ) as error:
        raise provider_error(error) from error
    return AIChatResponse(
        provider=result.provider,
        model=result.model,
        response=result.response,
    )

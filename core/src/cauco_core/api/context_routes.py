from typing import Annotated

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, StringConstraints

from cauco_core.context.builder import ContextBuilder
from cauco_core.context.models import ContextIntent, ContextPackage
from cauco_core.memory.models import MemoryKind, MemoryLayer, MemoryObjectSummary

router = APIRouter(prefix="/api/context", tags=["context"])
QuestionText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8000)
]


class ContextAnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: QuestionText


class ContextAnalyzeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str
    intent: ContextIntent
    layers: list[MemoryLayer]
    kinds: list[MemoryKind]
    reasoning: list[str]
    memory_objects: list[MemoryObjectSummary]
    generated_at: str

    @classmethod
    def from_package(cls, package: ContextPackage) -> "ContextAnalyzeResponse":
        return cls(
            question=package.question,
            intent=package.detected_intent,
            layers=package.selected_layers,
            kinds=package.selected_kinds,
            reasoning=package.reasoning,
            memory_objects=package.selected_memory_objects,
            generated_at=package.generated_at.isoformat(),
        )


class ContextIntentsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intents: list[ContextIntent]


def context_builder(request: Request) -> ContextBuilder:
    return request.app.state.context_builder


@router.post("/analyze", response_model=ContextAnalyzeResponse)
def analyze_context(
    payload: ContextAnalyzeRequest,
    request: Request,
) -> ContextAnalyzeResponse:
    package = context_builder(request).build(payload.question)
    return ContextAnalyzeResponse.from_package(package)


@router.get("/intents", response_model=ContextIntentsResponse)
def list_context_intents(request: Request) -> ContextIntentsResponse:
    intents = context_builder(request).analyzer.supported_intents()
    return ContextIntentsResponse(intents=intents)

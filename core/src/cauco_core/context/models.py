from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from cauco_core.memory.models import MemoryKind, MemoryLayer, MemoryObjectSummary


class ContextModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContextIntent(StrEnum):
    PLANNING = "planning"
    PROJECT = "project"
    DECISION = "decision"
    RELATIONSHIP = "relationship"
    RESEARCH = "research"
    MEETING = "meeting"
    REPORT = "report"
    IDENTITY = "identity"
    GENERAL = "general"


class IntentAnalysis(ContextModel):
    intent: ContextIntent
    score: int = Field(ge=0)
    matched_keywords: list[str]


class ContextPackage(ContextModel):
    question: str
    detected_intent: ContextIntent
    selected_layers: list[MemoryLayer]
    selected_kinds: list[MemoryKind]
    selected_memory_objects: list[MemoryObjectSummary]
    reasoning: list[str]
    generated_at: datetime

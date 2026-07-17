from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MemoryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MemoryKind(StrEnum):
    IDENTITY = "identity"
    PROJECTS = "projects"
    TASKS = "tasks"
    DECISIONS = "decisions"
    RELATIONSHIPS = "relationships"
    RULES = "rules"
    RESEARCH = "research"
    MEETINGS = "meetings"
    REPORTS = "reports"
    DAILY = "daily"
    GENERAL = "general"
    UNKNOWN = "unknown"


class MemoryLayer(StrEnum):
    SESSION = "session"
    WORKING = "working"
    LONG_TERM = "long_term"
    ARCHIVE = "archive"
    GOVERNANCE = "governance"
    IDENTITY = "identity"
    UNKNOWN = "unknown"


class MemoryObject(MemoryModel):
    id: str
    name: str
    kind: MemoryKind
    layer: MemoryLayer
    path: str
    relative_path: str
    title: str
    content: str
    preview: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    modified_at: datetime | None = None
    size_bytes: int = Field(ge=0)
    classification_confidence: float = Field(ge=0, le=1)
    classification_reasons: list[str]


class MemoryObjectSummary(MemoryModel):
    id: str
    name: str
    kind: MemoryKind
    layer: MemoryLayer
    path: str
    relative_path: str
    title: str
    preview: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    modified_at: datetime | None = None
    size_bytes: int = Field(ge=0)
    classification_confidence: float = Field(ge=0, le=1)
    classification_reasons: list[str]

    @classmethod
    def from_object(cls, memory: MemoryObject) -> "MemoryObjectSummary":
        return cls.model_validate(memory.model_dump(exclude={"content"}))


class MemoryRegistrySummary(MemoryModel):
    total: int = Field(ge=0)
    by_kind: dict[MemoryKind, int]
    by_layer: dict[MemoryLayer, int]


class MemoryEngineStatus(MemoryModel):
    status: str
    refreshed_at: datetime | None
    summary: MemoryRegistrySummary


class MemoryObjectsResponse(MemoryModel):
    objects: list[MemoryObjectSummary]
    count: int = Field(ge=0)


class MemoryFileMetadata(MemoryModel):
    relative_path: str
    name: str
    size: int = Field(ge=0)
    modified_at: datetime | None = None
    title: str


class MemoryFileContent(MemoryFileMetadata):
    content: str


class MemorySearchResult(MemoryModel):
    relative_path: str
    title: str
    score: int = Field(gt=0)
    matched_terms: list[str]
    excerpt: str


class MemoryFilesResponse(MemoryModel):
    files: list[MemoryFileMetadata]
    count: int = Field(ge=0)


class MemorySearchResponse(MemoryModel):
    query: str
    results: list[MemorySearchResult]
    count: int = Field(ge=0)


class MemoryContext(MemoryModel):
    text: str
    sources: list[str]

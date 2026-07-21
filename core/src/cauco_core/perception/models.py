from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PerceptionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PerceptionCapability(StrEnum):
    READ = "read"
    SEARCH = "search"
    REFRESH = "refresh"
    WATCH = "watch"


class PerceptionModality(StrEnum):
    TEXT = "text"
    VOICE = "voice"
    FILE = "file"
    EMAIL = "email"
    CALENDAR = "calendar"
    REPOSITORY = "repository"
    APPLICATION = "application"
    SYSTEM_EVENT = "system_event"


class PerceptionSourceStatus(StrEnum):
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class PerceptionSourceMetadata(PerceptionModel):
    source_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    capabilities: frozenset[PerceptionCapability] = Field(default_factory=frozenset)


class PerceptionRequest(PerceptionModel):
    query: str | None = None
    since: datetime | None = None
    limit: int = Field(default=20, ge=1, le=100)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize_query(self) -> "PerceptionRequest":
        if self.query is not None:
            normalized = self.query.strip()
            self.query = normalized or None
        return self


class PerceptionSignal(PerceptionModel):
    signal_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    modality: PerceptionModality
    observed_at: datetime
    content: str
    title: str | None = None
    reference: str | None = None
    confidence: float = Field(default=1.0, ge=0, le=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PerceptionBatch(PerceptionModel):
    source_id: str = Field(min_length=1)
    signals: tuple[PerceptionSignal, ...]
    collected_at: datetime

    @model_validator(mode="after")
    def validate_signal_sources(self) -> "PerceptionBatch":
        mismatched = tuple(
            signal.signal_id
            for signal in self.signals
            if signal.source_id != self.source_id
        )
        if mismatched:
            raise ValueError(
                "Every perception signal must belong to the batch source."
            )
        return self


class PerceptionHealth(PerceptionModel):
    source_id: str = Field(min_length=1)
    status: PerceptionSourceStatus
    checked_at: datetime
    message: str | None = None

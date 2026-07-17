from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, StringConstraints

from cauco_core.memory.models import MemoryKind, MemoryLayer

InstructionText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)
]
OptionalLabel = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]


class MemoryWritingModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MemoryWriteOperation(StrEnum):
    ADD_TASK = "add_task"
    ADD_DECISION = "add_decision"
    ADD_RELATIONSHIP_NOTE = "add_relationship_note"
    ADD_PROJECT_NOTE = "add_project_note"


class MemoryWriteProposalState(StrEnum):
    PENDING = "pending"
    APPLIED = "applied"
    EXPIRED = "expired"


class MemoryWriteRequest(MemoryWritingModel):
    instruction: InstructionText
    operation: MemoryWriteOperation | None = None
    project: OptionalLabel | None = None
    person: OptionalLabel | None = None
    requested_date: date | None = None


class MemoryWriteProposal(MemoryWritingModel):
    proposal_id: str
    operation: MemoryWriteOperation
    target_file: str
    target_kind: MemoryKind
    target_layer: MemoryLayer
    target_section: str
    normalized_content: str
    markdown_preview: str
    original_instruction: str
    reasoning: list[str]
    warnings: list[str]
    requires_confirmation: bool
    created_at: datetime


class MemoryWriteOperationInfo(MemoryWritingModel):
    operation: MemoryWriteOperation
    target_file: str


class MemoryWriteOperationsResponse(MemoryWritingModel):
    operations: list[MemoryWriteOperationInfo]


class StoredMemoryWriteProposal(MemoryWritingModel):
    proposal: MemoryWriteProposal
    state: MemoryWriteProposalState
    created_at: datetime
    expires_at: datetime
    applied_at: datetime | None = None


class MemoryWriteConfirmRequest(MemoryWritingModel):
    confirm: Any = None


class MemoryWriteApplicationResult(MemoryWritingModel):
    proposal_id: str
    state: MemoryWriteProposalState
    operation: MemoryWriteOperation
    target_file: str
    target_section: str
    applied_markdown: str
    memory_refreshed: bool
    applied_at: datetime
    warnings: list[str]

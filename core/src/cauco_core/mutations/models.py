import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any


class MutationPreviewStatus(StrEnum):
    PENDING_CONFIRMATION = "pending_confirmation"
    CONFIRMED = "confirmed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    CONSUMED = "consumed"


@dataclass(frozen=True, slots=True)
class MutationPreview:
    preview_id: str
    execution_id: str
    review_id: str
    step_index: int
    tool_id: str
    operation_id: str
    target: str | None
    normalized_arguments: Mapping[str, Any]
    before_state: Mapping[str, Any]
    proposed_after_state: Mapping[str, Any]
    diff_preview: str
    preview_digest: str
    confirmation_phrase: str
    created_at: datetime
    expires_at: datetime
    status: MutationPreviewStatus
    warning: str = "Preview creation performs no mutation. Confirmation is single-use."

    def __post_init__(self) -> None:
        if not re.fullmatch(r"mutprev_[A-Za-z0-9_-]{20,}", self.preview_id):
            raise ValueError("Mutation preview ID must be opaque and URL-safe.")
        if not re.fullmatch(r"[0-9a-f]{64}", self.preview_digest):
            raise ValueError("Mutation preview digest must be SHA-256.")
        if self.expires_at <= self.created_at:
            raise ValueError("Mutation preview expiration is invalid.")
        object.__setattr__(self, "normalized_arguments", freeze(self.normalized_arguments))
        object.__setattr__(self, "before_state", freeze(self.before_state))
        object.__setattr__(self, "proposed_after_state", freeze(self.proposed_after_state))


def freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze(item) for item in value)
    return value


class MutationError(RuntimeError):
    pass


class MutationNotFoundError(MutationError):
    pass


class MutationConflictError(MutationError):
    pass


class MutationValidationError(MutationError):
    pass


class MutationForbiddenError(MutationError):
    pass


class MutationCapacityError(MutationError):
    pass

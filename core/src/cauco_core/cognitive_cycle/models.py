from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class CognitiveCycleSnapshot:
    review_id: str
    current_stage: str
    overall_status: str
    blocked: bool
    terminal: bool
    awaiting_human_action: bool
    next_permitted_action: str | None
    safe_endpoint: str | None
    related_record_ids: Mapping[str, str | None] = field(default_factory=dict)
    candidate_counts: Mapping[str, int] = field(default_factory=dict)
    proposal_counts: Mapping[str, int] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    method: str = "deterministic_cognitive_cycle_observer_v1"

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "related_record_ids", MappingProxyType(dict(self.related_record_ids))
        )
        object.__setattr__(self, "candidate_counts", MappingProxyType(dict(self.candidate_counts)))
        object.__setattr__(self, "proposal_counts", MappingProxyType(dict(self.proposal_counts)))

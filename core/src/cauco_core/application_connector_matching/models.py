"""Immutable application-to-connector matching models."""

from dataclasses import dataclass
from enum import StrEnum


class MatchConfidence(StrEnum):
    EXACT_BUNDLE_ID = "exact_bundle_id"
    EXPLICIT_PROVIDER_MAPPING = "explicit_provider_mapping"
    AMBIGUOUS = "ambiguous"
    NO_MATCH = "no_match"


class MatchStatus(StrEnum):
    MATCHED_REGISTERED_CONNECTOR = "matched_registered_connector"
    MATCHED_KNOWN_PROVIDER = "matched_known_provider"
    AMBIGUOUS = "ambiguous"
    UNSUPPORTED = "unsupported"
    UNAVAILABLE_METADATA = "unavailable_metadata"
    NO_MATCH = "no_match"


@dataclass(frozen=True, slots=True)
class ProviderMapping:
    provider_id: str
    bundle_identifiers: tuple[str, ...]
    application_family: str | None = None
    platform: str | None = None
    name_message_key: str = "provider.name"
    description_message_key: str = "provider.description"
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.provider_id or not self.provider_id.islower() or " " in self.provider_id:
            raise ValueError("Provider ID must be a lowercase machine identifier.")
        if not self.bundle_identifiers or len(self.bundle_identifiers) > 100:
            raise ValueError("Bundle identifiers are invalid.")
        if len(set(self.bundle_identifiers)) != len(self.bundle_identifiers):
            raise ValueError("Duplicate bundle identifiers are not allowed.")
        object.__setattr__(self, "bundle_identifiers", tuple(sorted(self.bundle_identifiers)))
        object.__setattr__(self, "limitations", tuple(self.limitations))


@dataclass(frozen=True, slots=True)
class ApplicationConnectorMatch:
    inventory_id: str
    display_name: str
    bundle_identifier: str | None
    application_availability: str
    matched_provider_ids: tuple[str, ...] = ()
    matched_registered_connector_ids: tuple[str, ...] = ()
    status: MatchStatus = MatchStatus.NO_MATCH
    confidence: MatchConfidence = MatchConfidence.NO_MATCH
    reason_codes: tuple[str, ...] = ()
    has_registered_connector: bool = False
    connector_available: bool = False
    permissions_evaluated: bool = False
    routing_evaluated: bool = False
    candidate_connector_count: int = 0
    limitations: tuple[str, ...] = ()
    method: str = "application-connector-matching-v1"

    def __post_init__(self) -> None:
        if not self.inventory_id or not self.display_name:
            raise ValueError("Application identity is required.")
        if self.candidate_connector_count < 0:
            raise ValueError("Candidate count cannot be negative.")
        object.__setattr__(
            self, "matched_provider_ids", tuple(sorted(set(self.matched_provider_ids)))
        )
        object.__setattr__(
            self,
            "matched_registered_connector_ids",
            tuple(sorted(set(self.matched_registered_connector_ids))),
        )
        object.__setattr__(self, "reason_codes", tuple(sorted(set(self.reason_codes))))
        object.__setattr__(self, "limitations", tuple(self.limitations))


@dataclass(frozen=True, slots=True)
class MatchingSummary:
    inventory_count: int
    matched_registered_connector_count: int
    matched_known_provider_count: int
    ambiguous_count: int
    unsupported_count: int
    no_match_count: int
    last_inventory_scan_at: object | None
    connector_registry_count: int
    warnings: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    method: str = "application-connector-matching-v1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "limitations", tuple(self.limitations))

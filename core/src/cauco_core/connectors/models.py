"""Validated immutable models for the metadata-only connector runtime."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any

IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)*$")
LOCALE = re.compile(r"^(en|es|fi|sv)(?:-[A-Z][a-z]{2,3}|-[A-Z]{2}|-[0-9]{3})*$")
MAX_DEPTH = 8
MAX_ITEMS = 100
MAX_STRING = 500


class ConnectorAvailability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


class ConnectorHealth(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ConnectorPlatform(StrEnum):
    MACOS = "macos"
    CROSS_PLATFORM = "cross_platform"
    UNKNOWN = "unknown"


class ConnectorAccessMode(StrEnum):
    INSPECT = "inspect"
    READ = "read"
    DRAFT = "draft"
    WRITE = "write"
    EXECUTE = "execute"
    DELETE = "delete"
    EXTERNAL_SEND = "external_send"


class ConnectorRiskLevel(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class PermissionState(StrEnum):
    UNKNOWN = "unknown"
    NOT_REQUESTED = "not_requested"
    PENDING = "pending"
    GRANTED = "granted"
    DENIED = "denied"
    RESTRICTED = "restricted"
    UNAVAILABLE = "unavailable"


class PermissionDecision(StrEnum):
    ELIGIBLE = "eligible"
    UNAVAILABLE = "unavailable"
    DENIED = "denied"
    AWAITING_PERMISSION = "awaiting_permission"
    AWAITING_CONFIRMATION = "awaiting_confirmation"


def _identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError(f"Invalid {label}.")
    return value


def _text(value: str | None, label: str, required: bool = False) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value or len(value) > MAX_STRING:
        raise ValueError(f"Invalid {label}.")
    return value


def _message_key(value: str, label: str) -> str:
    return _identifier(value, label)


def _freeze(value: Any, depth: int = 0) -> Any:
    if depth > MAX_DEPTH:
        raise ValueError("JSON value is nested too deeply.")
    if value is None or isinstance(value, (str, bool, int)):
        if isinstance(value, str) and len(value) > MAX_STRING:
            raise ValueError("JSON string is too long.")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON numbers must be finite.")
        return value
    if isinstance(value, Mapping):
        if len(value) > MAX_ITEMS:
            raise ValueError("JSON mapping is too large.")
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > MAX_STRING:
                raise ValueError("JSON mapping keys must be bounded strings.")
            result[key] = _freeze(item, depth + 1)
        return MappingProxyType(result)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        if len(value) > MAX_ITEMS:
            raise ValueError("JSON sequence is too large.")
        return tuple(_freeze(item, depth + 1) for item in value)
    raise ValueError("Value is not JSON-safe.")


def _locale(value: str) -> str:
    if not isinstance(value, str) or not LOCALE.fullmatch(value):
        raise ValueError("Locale must be a supported BCP 47 language tag.")
    return value


def _unique_ids(values: Sequence[str], label: str) -> tuple[str, ...]:
    result = tuple(_identifier(value, label) for value in values)
    if len(set(result)) != len(result):
        raise ValueError(f"Duplicate {label}.")
    return tuple(sorted(result))


@dataclass(frozen=True, slots=True)
class ConnectorIdentity:
    connector_id: str
    provider_id: str
    version: str
    availability: ConnectorAvailability
    health: ConnectorHealth
    platform: ConnectorPlatform
    local: bool
    priority: int = 0
    application_bundle_id: str | None = None
    name_message_key: str = "connector.name"
    description_message_key: str = "connector.description"
    capability_ids: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    diagnostics: Mapping[str, str | int | bool | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _identifier(self.connector_id, "connector ID")
        _identifier(self.provider_id, "provider ID")
        _text(self.version, "version", required=True)
        if not -1000 <= self.priority <= 1000:
            raise ValueError("Connector priority is out of bounds.")
        _text(self.application_bundle_id, "application bundle ID")
        _message_key(self.name_message_key, "name message key")
        _message_key(self.description_message_key, "description message key")
        object.__setattr__(
            self, "capability_ids", _unique_ids(self.capability_ids, "capability ID")
        )
        object.__setattr__(self, "limitations", tuple(self.limitations))
        object.__setattr__(self, "diagnostics", _freeze(self.diagnostics))


@dataclass(frozen=True, slots=True)
class CapabilityDefinition:
    capability_id: str
    domain: str
    action: str
    semantic_category: str
    access_mode: ConnectorAccessMode
    risk_level: ConnectorRiskLevel
    confirmation_required: bool = False
    mutates_external_state: bool = False
    exposes_personal_data: bool = False
    required_permission_ids: tuple[str, ...] = ()
    name_message_key: str = "capability.name"
    description_message_key: str = "capability.description"
    confirmation_message_key: str = "capability.confirmation"
    limitations: tuple[str, ...] = ()
    input_metadata: Mapping[str, Any] = field(default_factory=dict)
    output_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _identifier(self.capability_id, "capability ID")
        _identifier(self.domain, "domain")
        _identifier(self.action, "action")
        _identifier(self.semantic_category, "semantic category")
        _unique_ids(self.required_permission_ids, "permission ID")
        object.__setattr__(
            self,
            "required_permission_ids",
            _unique_ids(self.required_permission_ids, "permission ID"),
        )
        for key, label in (
            (self.name_message_key, "name message key"),
            (self.description_message_key, "description message key"),
            (self.confirmation_message_key, "confirmation message key"),
        ):
            _message_key(key, label)
        if (
            self.access_mode in (ConnectorAccessMode.INSPECT, ConnectorAccessMode.READ)
            and self.mutates_external_state
        ):
            raise ValueError("Inspect and read capabilities cannot mutate state.")
        if (
            self.access_mode in (ConnectorAccessMode.DELETE, ConnectorAccessMode.EXTERNAL_SEND)
            and not self.mutates_external_state
        ):
            raise ValueError("Delete and external-send capabilities must mutate state.")
        if (
            self.access_mode in (ConnectorAccessMode.DELETE, ConnectorAccessMode.EXTERNAL_SEND)
            and not self.confirmation_required
        ):
            raise ValueError("Delete and external-send capabilities require confirmation.")
        if (
            self.risk_level in (ConnectorRiskLevel.HIGH, ConnectorRiskLevel.CRITICAL)
            and not self.confirmation_required
        ):
            raise ValueError("High and critical risk capabilities require confirmation.")
        object.__setattr__(self, "input_metadata", _freeze(self.input_metadata))
        object.__setattr__(self, "output_metadata", _freeze(self.output_metadata))
        object.__setattr__(self, "limitations", tuple(self.limitations))


@dataclass(frozen=True, slots=True)
class PermissionDefinition:
    permission_id: str
    scope: str
    state: PermissionState
    authority: str
    user_interaction_required: bool
    revocable: bool
    explanation_message_key: str = "permission.explanation"
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.permission_id, "permission ID")
        _text(self.scope, "permission scope", required=True)
        _text(self.authority, "permission authority", required=True)
        _message_key(self.explanation_message_key, "explanation message key")
        object.__setattr__(self, "limitations", tuple(self.limitations))


@dataclass(frozen=True, slots=True)
class ConnectorRequest:
    request_id: str
    capability_id: str
    preferred_connector_id: str | None
    requester_id: str
    request_locale: str
    response_locale: str
    interface_locale: str
    fallback_locale: str = "en"
    arguments: Mapping[str, Any] = field(default_factory=dict)
    explicit_user_request: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now().astimezone())
    confirmation_request_id: str | None = None

    def __post_init__(self) -> None:
        _identifier(self.request_id, "request ID")
        _identifier(self.capability_id, "capability ID")
        _identifier(self.requester_id, "requester ID")
        if self.preferred_connector_id is not None:
            _identifier(self.preferred_connector_id, "preferred connector ID")
        for locale in (
            self.request_locale,
            self.response_locale,
            self.interface_locale,
            self.fallback_locale,
        ):
            _locale(locale)
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("Timestamp must be timezone-aware.")
        if self.confirmation_request_id is not None:
            _identifier(self.confirmation_request_id, "confirmation request ID")
        object.__setattr__(self, "arguments", _freeze(self.arguments))


@dataclass(frozen=True, slots=True)
class PolicyEvaluation:
    decision: PermissionDecision
    reason_code: str
    missing_permission_ids: tuple[str, ...] = ()
    denied_permission_ids: tuple[str, ...] = ()
    confirmation_required: bool = False
    executable: bool = False
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.reason_code, "reason code")
        object.__setattr__(
            self, "missing_permission_ids", tuple(sorted(self.missing_permission_ids))
        )
        object.__setattr__(self, "denied_permission_ids", tuple(sorted(self.denied_permission_ids)))
        object.__setattr__(self, "limitations", tuple(self.limitations))


@dataclass(frozen=True, slots=True)
class RoutingResult:
    request_id: str
    capability_id: str
    selected_connector_id: str | None
    eligible_connector_ids: tuple[str, ...]
    rejected_connector_reason_codes: Mapping[str, str]
    policy_evaluations: Mapping[str, PolicyEvaluation]
    confirmation_required: bool
    executable: bool
    limitations: tuple[str, ...] = ()
    method: str = "connector-routing-v1"

    def __post_init__(self) -> None:
        _identifier(self.request_id, "request ID")
        _identifier(self.capability_id, "capability ID")
        object.__setattr__(self, "eligible_connector_ids", tuple(self.eligible_connector_ids))
        object.__setattr__(
            self, "rejected_connector_reason_codes", _freeze(self.rejected_connector_reason_codes)
        )
        if not isinstance(self.policy_evaluations, Mapping):
            raise ValueError("Policy evaluations must be a mapping.")
        object.__setattr__(
            self, "policy_evaluations", MappingProxyType(dict(self.policy_evaluations))
        )
        object.__setattr__(self, "limitations", tuple(self.limitations))

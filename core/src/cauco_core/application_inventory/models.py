"""Immutable application inventory models."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType

ID_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,99}$")
ARCHITECTURES = {"arm64", "x86_64", "universal", "unknown"}
MAX_TEXT = 500
MAX_ITEMS = 100


class ApplicationSource(StrEnum):
    SYSTEM_APPLICATIONS = "system_applications"
    LOCAL_APPLICATIONS = "local_applications"
    USER_APPLICATIONS = "user_applications"
    EXPLICIT_PATH = "explicit_path"


class ApplicationAvailability(StrEnum):
    AVAILABLE = "available"
    UNREADABLE = "unreadable"
    INVALID_BUNDLE = "invalid_bundle"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


def _id(value: str, label: str) -> str:
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
        raise ValueError(f"Invalid {label}.")
    return value


def _text(value: str, label: str, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > MAX_TEXT:
        raise ValueError(f"Invalid {label}.")
    return value


def _freeze(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        if len(value) > MAX_ITEMS:
            raise ValueError("Mapping is too large.")
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if len(value) > MAX_ITEMS:
            raise ValueError("Sequence is too large.")
        return tuple(_freeze(item) for item in value)
    raise ValueError("Value cannot be made immutable.")


def normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return " ".join(
        "".join(char for char in normalized if not unicodedata.combining(char)).casefold().split()
    )


@dataclass(frozen=True, slots=True)
class ApplicationBundleSnapshot:
    inventory_id: str
    display_name: str
    normalized_name: str
    bundle_identifier: str | None
    bundle_path: str
    bundle_filename: str
    version: str | None
    build_version: str | None
    minimum_macos_version: str | None
    source: ApplicationSource
    availability: ApplicationAvailability
    architecture: str = "unknown"
    localizations: tuple[str, ...] = ()
    url_schemes: tuple[str, ...] = ()
    document_types: tuple[str, ...] = ()
    diagnostic_reason_codes: tuple[str, ...] = ()
    discovered_at: datetime = field(default_factory=lambda: datetime.now().astimezone())
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _id(self.inventory_id, "inventory ID")
        _text(self.display_name, "display name")
        _text(self.bundle_path, "bundle path")
        _text(self.bundle_filename, "bundle filename")
        _text(self.bundle_identifier, "bundle identifier", optional=True)
        for value, label in (
            (self.version, "version"),
            (self.build_version, "build version"),
            (self.minimum_macos_version, "minimum macOS version"),
        ):
            _text(value, label, optional=True)
        if self.architecture not in ARCHITECTURES:
            raise ValueError("Invalid architecture.")
        if self.discovered_at.tzinfo is None or self.discovered_at.utcoffset() is None:
            raise ValueError("Timestamp must be timezone-aware.")
        object.__setattr__(self, "normalized_name", normalize_name(self.display_name))
        object.__setattr__(self, "localizations", tuple(sorted(set(self.localizations))))
        object.__setattr__(self, "url_schemes", tuple(sorted(set(self.url_schemes))))
        object.__setattr__(self, "document_types", tuple(sorted(set(self.document_types))))
        object.__setattr__(
            self, "diagnostic_reason_codes", tuple(sorted(set(self.diagnostic_reason_codes)))
        )
        object.__setattr__(self, "limitations", tuple(self.limitations))


@dataclass(frozen=True, slots=True)
class InventoryStatus:
    scan_state: str
    application_count: int
    source_counts: Mapping[str, int]
    availability_counts: Mapping[str, int]
    last_scan_at: datetime | None
    warnings: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    method: str = "mac-application-inventory-v1"

    def __post_init__(self) -> None:
        if self.application_count < 0:
            raise ValueError("Application count cannot be negative.")
        if self.last_scan_at is not None and self.last_scan_at.tzinfo is None:
            raise ValueError("Timestamp must be timezone-aware.")
        object.__setattr__(self, "source_counts", MappingProxyType(dict(self.source_counts)))
        object.__setattr__(
            self, "availability_counts", MappingProxyType(dict(self.availability_counts))
        )
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "limitations", tuple(self.limitations))

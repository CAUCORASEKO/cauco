"""Explicitly refreshed in-memory application inventory service."""

from __future__ import annotations

from threading import RLock

from .exceptions import ApplicationNotFoundError
from .models import (
    ApplicationAvailability,
    ApplicationBundleSnapshot,
    ApplicationSource,
    InventoryStatus,
    normalize_name,
)


class ApplicationInventoryService:
    def __init__(self, scanner) -> None:
        self.scanner = scanner
        self._items: tuple[ApplicationBundleSnapshot, ...] = ()
        self._last_scan_at = None
        self._lock = RLock()

    def refresh(self) -> tuple[ApplicationBundleSnapshot, ...]:
        scanned = self.scanner.scan()
        with self._lock:
            self._items = tuple(scanned)
            self._last_scan_at = scanned[0].discovered_at if scanned else None
            return self._items

    def list(
        self,
        source: ApplicationSource | None = None,
        availability: ApplicationAvailability | None = None,
        architecture: str | None = None,
        bundle_identifier: str | None = None,
        query: str | None = None,
        limit: int = 100,
    ) -> tuple[ApplicationBundleSnapshot, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("Limit must be between 1 and 100.")
        with self._lock:
            result = self._items
        normalized_query = normalize_name(query) if query else None
        result = tuple(
            item
            for item in result
            if (source is None or item.source == source)
            and (availability is None or item.availability == availability)
            and (architecture is None or item.architecture == architecture)
            and (bundle_identifier is None or item.bundle_identifier == bundle_identifier)
            and (
                normalized_query is None
                or normalized_query in item.normalized_name
                or normalized_query in normalize_name(item.bundle_identifier or "")
            )
        )
        return result[:limit]

    def get(self, inventory_id: str) -> ApplicationBundleSnapshot:
        with self._lock:
            for item in self._items:
                if item.inventory_id == inventory_id:
                    return item
        raise ApplicationNotFoundError("Application was not found.")

    def status(self) -> InventoryStatus:
        with self._lock:
            items = self._items
            last_scan = self._last_scan_at
        source_counts = {
            source.value: sum(item.source == source for item in items)
            for source in ApplicationSource
        }
        availability_counts = {
            state.value: sum(item.availability == state for item in items)
            for state in ApplicationAvailability
        }
        return InventoryStatus(
            "ready" if last_scan else "empty",
            len(items),
            source_counts,
            availability_counts,
            last_scan,
            limitations=("Inventory is refreshed explicitly and does not monitor applications.",),
        )

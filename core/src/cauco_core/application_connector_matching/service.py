"""Explicitly refreshed in-memory matching service."""

from threading import RLock

from .models import MatchingSummary, MatchStatus


class ApplicationConnectorMatchingService:
    def __init__(self, inventory_service, resolver) -> None:
        self.inventory_service = inventory_service
        self.resolver = resolver
        self._matches = ()
        self._lock = RLock()

    def refresh(self):
        applications = self.inventory_service.list(limit=100)
        matches = tuple(
            sorted(
                (self.resolver.resolve(item) for item in applications),
                key=lambda item: (
                    item.display_name.casefold(),
                    item.bundle_identifier or "",
                    item.inventory_id,
                ),
            )
        )
        with self._lock:
            self._matches = matches
        return matches

    def list(
        self,
        status=None,
        confidence=None,
        provider_id=None,
        has_registered_connector=None,
        connector_available=None,
        limit=100,
    ):
        if not 1 <= limit <= 100:
            raise ValueError("Limit must be between 1 and 100.")
        with self._lock:
            result = self._matches
        result = tuple(
            item
            for item in result
            if (status is None or item.status == status)
            and (confidence is None or item.confidence == confidence)
            and (provider_id is None or provider_id in item.matched_provider_ids)
            and (
                has_registered_connector is None
                or item.has_registered_connector == has_registered_connector
            )
            and (connector_available is None or item.connector_available == connector_available)
        )
        return result[:limit]

    def get(self, inventory_id):
        for item in self.list(limit=100):
            if item.inventory_id == inventory_id:
                return item
        raise KeyError(inventory_id)

    def summary(self):
        items = self.list(limit=100)
        counts = {state: sum(item.status == state for item in items) for state in MatchStatus}
        return MatchingSummary(
            len(items),
            counts[MatchStatus.MATCHED_REGISTERED_CONNECTOR],
            counts[MatchStatus.MATCHED_KNOWN_PROVIDER],
            counts[MatchStatus.AMBIGUOUS],
            counts[MatchStatus.UNSUPPORTED],
            counts[MatchStatus.NO_MATCH],
            None,
            len(self.resolver.connectors.list()),
            limitations=("Matching does not evaluate permissions or routing.",),
        )

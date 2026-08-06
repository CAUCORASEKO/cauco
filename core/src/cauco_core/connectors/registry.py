"""Thread-safe deterministic connector registry."""

from threading import RLock

from .exceptions import ConnectorNotFoundError, DuplicateConnectorError
from .models import (
    CapabilityDefinition,
    ConnectorAvailability,
    ConnectorIdentity,
    ConnectorPlatform,
)
from .protocol import Connector


def _limit(limit: int | None) -> int | None:
    if limit is not None and not 1 <= limit <= 100:
        raise ValueError("Limit must be between 1 and 100.")
    return limit


class ConnectorRegistry:
    def __init__(self) -> None:
        self._connectors: dict[str, Connector] = {}
        self._lock = RLock()

    def register(self, connector: Connector) -> None:
        connector_id = connector.metadata.connector_id
        with self._lock:
            if connector_id in self._connectors:
                raise DuplicateConnectorError(f"Connector '{connector_id}' is already registered.")
            self._connectors[connector_id] = connector

    def get_metadata(self, connector_id: str) -> ConnectorIdentity:
        with self._lock:
            connector = self._connectors.get(connector_id)
        if connector is None:
            raise ConnectorNotFoundError(f"Unknown connector '{connector_id}'.")
        return connector.metadata

    def list(self, limit: int | None = None) -> tuple[ConnectorIdentity, ...]:
        _limit(limit)
        with self._lock:
            result = tuple(self._connectors[key].metadata for key in sorted(self._connectors))
        return result[:limit]

    def capabilities(self, limit: int | None = None) -> tuple[CapabilityDefinition, ...]:
        _limit(limit)
        with self._lock:
            result = [
                item for connector in self._connectors.values() for item in connector.capabilities()
            ]
        return tuple(sorted(result, key=lambda item: item.capability_id))[:limit]

    def discover(
        self,
        capability_id: str,
        *,
        provider_id: str | None = None,
        availability: ConnectorAvailability | None = None,
        platform: ConnectorPlatform | None = None,
        limit: int | None = None,
    ) -> tuple[ConnectorIdentity, ...]:
        _limit(limit)
        with self._lock:
            result = []
            for connector in self._connectors.values():
                metadata = connector.metadata
                if capability_id not in metadata.capability_ids:
                    continue
                if provider_id is not None and metadata.provider_id != provider_id:
                    continue
                if availability is not None and metadata.availability != availability:
                    continue
                if platform is not None and metadata.platform != platform:
                    continue
                result.append(metadata)
        result.sort(key=lambda item: (-item.priority, item.connector_id))
        return tuple(result[:limit])

    def _get_connector(self, connector_id: str) -> Connector:
        with self._lock:
            connector = self._connectors.get(connector_id)
        if connector is None:
            raise ConnectorNotFoundError(f"Unknown connector '{connector_id}'.")
        return connector

from abc import ABC, abstractmethod

from cauco_core.perception.models import (
    PerceptionBatch,
    PerceptionCapability,
    PerceptionHealth,
    PerceptionRequest,
    PerceptionSourceMetadata,
)


class PerceptionSource(ABC):
    @property
    @abstractmethod
    def metadata(self) -> PerceptionSourceMetadata:
        """Describe the source and its supported perception capabilities."""

    @abstractmethod
    def health(self) -> PerceptionHealth:
        """Return the current availability of the source."""

    @abstractmethod
    def collect(self, request: PerceptionRequest) -> PerceptionBatch:
        """Collect signals matching the perception request."""

    def supports(self, capability: PerceptionCapability) -> bool:
        return capability in self.metadata.capabilities

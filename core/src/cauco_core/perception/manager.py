from collections.abc import Iterable
from datetime import UTC, datetime

from pydantic import Field

from cauco_core.perception.models import (
    PerceptionBatch,
    PerceptionCapability,
    PerceptionModel,
    PerceptionRequest,
    PerceptionSignal,
)
from cauco_core.perception.registry import PerceptionSourceRegistry


class PerceptionSourceError(PerceptionModel):
    source_id: str = Field(min_length=1)
    error_type: str = Field(min_length=1)
    message: str = Field(min_length=1)


class PerceptionCollectionResult(PerceptionModel):
    requested_source_ids: tuple[str, ...]
    successful_source_ids: tuple[str, ...]
    signals: tuple[PerceptionSignal, ...]
    errors: tuple[PerceptionSourceError, ...]
    collected_at: datetime

    @property
    def succeeded(self) -> bool:
        return not self.errors

    @property
    def partial(self) -> bool:
        return bool(self.successful_source_ids) and bool(self.errors)


class PerceptionManager:
    def __init__(self, registry: PerceptionSourceRegistry) -> None:
        self.registry = registry

    def collect_from(
        self,
        source_id: str,
        request: PerceptionRequest,
        *,
        required_capability: PerceptionCapability | None = None,
    ) -> PerceptionBatch:
        source = self.registry.get(source_id)

        if required_capability is not None and not source.supports(required_capability):
            raise ValueError(
                f"Perception source '{source_id}' does not support "
                f"capability '{required_capability.value}'."
            )

        batch = source.collect(request)

        if batch.source_id != source_id:
            raise ValueError(
                f"Perception source '{source_id}' returned a batch for "
                f"source '{batch.source_id}'."
            )

        return batch

    def collect_many(
        self,
        source_ids: Iterable[str],
        request: PerceptionRequest,
        *,
        required_capability: PerceptionCapability | None = None,
    ) -> PerceptionCollectionResult:
        normalized_source_ids = self._normalize_source_ids(source_ids)
        successful_source_ids: list[str] = []
        signals: list[PerceptionSignal] = []
        errors: list[PerceptionSourceError] = []

        for source_id in normalized_source_ids:
            try:
                batch = self.collect_from(
                    source_id,
                    request,
                    required_capability=required_capability,
                )
            except (KeyError, ValueError, RuntimeError) as error:
                errors.append(
                    PerceptionSourceError(
                        source_id=source_id,
                        error_type=type(error).__name__,
                        message=str(error),
                    )
                )
                continue

            successful_source_ids.append(source_id)
            signals.extend(batch.signals)

        signals.sort(
            key=lambda signal: (
                signal.observed_at,
                signal.source_id,
                signal.signal_id,
            )
        )

        return PerceptionCollectionResult(
            requested_source_ids=normalized_source_ids,
            successful_source_ids=tuple(successful_source_ids),
            signals=tuple(signals),
            errors=tuple(errors),
            collected_at=datetime.now(UTC),
        )

    def collect_all(
        self,
        request: PerceptionRequest,
        *,
        required_capability: PerceptionCapability | None = None,
    ) -> PerceptionCollectionResult:
        source_ids = (metadata.source_id for metadata in self.registry.list_metadata())
        return self.collect_many(
            source_ids,
            request,
            required_capability=required_capability,
        )

    @staticmethod
    def _normalize_source_ids(source_ids: Iterable[str]) -> tuple[str, ...]:
        normalized: list[str] = []
        seen: set[str] = set()

        for source_id in source_ids:
            clean_source_id = source_id.strip()
            if not clean_source_id:
                raise ValueError("Perception source identifiers cannot be blank.")
            if clean_source_id in seen:
                continue

            seen.add(clean_source_id)
            normalized.append(clean_source_id)

        return tuple(normalized)

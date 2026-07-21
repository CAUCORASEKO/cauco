from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from cauco_core.perception import (
    PerceptionBatch,
    PerceptionCapability,
    PerceptionHealth,
    PerceptionModality,
    PerceptionRequest,
    PerceptionSignal,
    PerceptionSource,
    PerceptionSourceMetadata,
    PerceptionSourceRegistry,
    PerceptionSourceStatus,
)


class StubPerceptionSource(PerceptionSource):
    def __init__(self, source_id: str = "stub") -> None:
        self._metadata = PerceptionSourceMetadata(
            source_id=source_id,
            name="Stub source",
            capabilities=frozenset(
                {
                    PerceptionCapability.READ,
                    PerceptionCapability.SEARCH,
                }
            ),
        )

    @property
    def metadata(self) -> PerceptionSourceMetadata:
        return self._metadata

    def health(self) -> PerceptionHealth:
        return PerceptionHealth(
            source_id=self.metadata.source_id,
            status=PerceptionSourceStatus.AVAILABLE,
            checked_at=datetime.now(UTC),
        )

    def collect(self, request: PerceptionRequest) -> PerceptionBatch:
        signal = PerceptionSignal(
            signal_id="signal-1",
            source_id=self.metadata.source_id,
            modality=PerceptionModality.TEXT,
            observed_at=datetime.now(UTC),
            content=request.query or "No query",
        )
        return PerceptionBatch(
            source_id=self.metadata.source_id,
            signals=(signal,),
            collected_at=datetime.now(UTC),
        )


def test_request_normalizes_blank_query() -> None:
    request = PerceptionRequest(query="   ")

    assert request.query is None


def test_source_reports_capabilities() -> None:
    source = StubPerceptionSource()

    assert source.supports(PerceptionCapability.READ)
    assert source.supports(PerceptionCapability.SEARCH)
    assert not source.supports(PerceptionCapability.WATCH)


def test_source_collects_a_valid_batch() -> None:
    source = StubPerceptionSource()

    batch = source.collect(PerceptionRequest(query="Aurora"))

    assert batch.source_id == "stub"
    assert len(batch.signals) == 1
    assert batch.signals[0].content == "Aurora"


def test_batch_rejects_signals_from_another_source() -> None:
    signal = PerceptionSignal(
        signal_id="signal-1",
        source_id="other",
        modality=PerceptionModality.TEXT,
        observed_at=datetime.now(UTC),
        content="Unexpected source",
    )

    with pytest.raises(ValidationError, match="batch source"):
        PerceptionBatch(
            source_id="expected",
            signals=(signal,),
            collected_at=datetime.now(UTC),
        )


def test_registry_registers_and_returns_sources() -> None:
    registry = PerceptionSourceRegistry()
    source = StubPerceptionSource()

    registry.register(source)

    assert registry.get("stub") is source
    assert registry.list_sources() == (source,)
    assert registry.list_metadata() == (source.metadata,)
    assert len(registry) == 1


def test_registry_lists_sources_deterministically() -> None:
    registry = PerceptionSourceRegistry()
    beta = StubPerceptionSource("beta")
    alpha = StubPerceptionSource("alpha")

    registry.register(beta)
    registry.register(alpha)

    assert tuple(source.metadata.source_id for source in registry.list_sources()) == (
        "alpha",
        "beta",
    )


def test_registry_rejects_duplicate_sources() -> None:
    registry = PerceptionSourceRegistry()
    registry.register(StubPerceptionSource())

    with pytest.raises(ValueError, match="already registered"):
        registry.register(StubPerceptionSource())


def test_registry_rejects_unknown_sources() -> None:
    registry = PerceptionSourceRegistry()

    with pytest.raises(KeyError, match="Unknown perception source"):
        registry.get("missing")

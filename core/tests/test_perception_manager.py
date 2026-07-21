from datetime import UTC, datetime, timedelta

import pytest

from cauco_core.perception import (
    PerceptionBatch,
    PerceptionCapability,
    PerceptionManager,
    PerceptionModality,
    PerceptionRequest,
    PerceptionSignal,
    PerceptionSource,
    PerceptionSourceMetadata,
    PerceptionSourceRegistry,
)


class ManagedStubSource(PerceptionSource):
    def __init__(
        self,
        source_id: str,
        *,
        capabilities: frozenset[PerceptionCapability] | None = None,
        observed_at: datetime | None = None,
        failure: Exception | None = None,
        returned_source_id: str | None = None,
    ) -> None:
        self._metadata = PerceptionSourceMetadata(
            source_id=source_id,
            name=f"Source {source_id}",
            capabilities=capabilities
            or frozenset(
                {
                    PerceptionCapability.READ,
                    PerceptionCapability.SEARCH,
                }
            ),
        )
        self._observed_at = observed_at or datetime.now(UTC)
        self._failure = failure
        self._returned_source_id = returned_source_id

    @property
    def metadata(self) -> PerceptionSourceMetadata:
        return self._metadata

    def health(self):
        raise NotImplementedError

    def collect(self, request: PerceptionRequest) -> PerceptionBatch:
        if self._failure is not None:
            raise self._failure

        batch_source_id = self._returned_source_id or self.metadata.source_id
        signal = PerceptionSignal(
            signal_id=f"{self.metadata.source_id}-signal",
            source_id=batch_source_id,
            modality=PerceptionModality.TEXT,
            observed_at=self._observed_at,
            content=request.query or "empty",
        )
        return PerceptionBatch(
            source_id=batch_source_id,
            signals=(signal,),
            collected_at=datetime.now(UTC),
        )


def make_manager(*sources: ManagedStubSource) -> PerceptionManager:
    registry = PerceptionSourceRegistry()
    for source in sources:
        registry.register(source)
    return PerceptionManager(registry)


def test_collect_from_single_source() -> None:
    manager = make_manager(ManagedStubSource("obsidian"))

    batch = manager.collect_from(
        "obsidian",
        PerceptionRequest(query="Aurora"),
        required_capability=PerceptionCapability.SEARCH,
    )

    assert batch.source_id == "obsidian"
    assert batch.signals[0].content == "Aurora"


def test_collect_from_rejects_unsupported_capability() -> None:
    source = ManagedStubSource(
        "calendar",
        capabilities=frozenset({PerceptionCapability.READ}),
    )
    manager = make_manager(source)

    with pytest.raises(ValueError, match="does not support"):
        manager.collect_from(
            "calendar",
            PerceptionRequest(query="today"),
            required_capability=PerceptionCapability.SEARCH,
        )


def test_collect_many_combines_and_orders_signals() -> None:
    now = datetime.now(UTC)
    manager = make_manager(
        ManagedStubSource("later", observed_at=now),
        ManagedStubSource("earlier", observed_at=now - timedelta(minutes=5)),
    )

    result = manager.collect_many(
        ("later", "earlier"),
        PerceptionRequest(query="pending"),
    )

    assert result.succeeded
    assert not result.partial
    assert result.successful_source_ids == ("later", "earlier")
    assert tuple(signal.source_id for signal in result.signals) == (
        "earlier",
        "later",
    )


def test_collect_many_isolates_source_failures() -> None:
    manager = make_manager(
        ManagedStubSource("healthy"),
        ManagedStubSource("broken", failure=RuntimeError("Connector unavailable")),
    )

    result = manager.collect_many(
        ("healthy", "broken"),
        PerceptionRequest(query="today"),
    )

    assert not result.succeeded
    assert result.partial
    assert result.successful_source_ids == ("healthy",)
    assert len(result.signals) == 1
    assert len(result.errors) == 1
    assert result.errors[0].source_id == "broken"
    assert result.errors[0].error_type == "RuntimeError"


def test_collect_many_reports_unknown_sources() -> None:
    manager = make_manager(ManagedStubSource("known"))

    result = manager.collect_many(
        ("known", "missing"),
        PerceptionRequest(),
    )

    assert result.partial
    assert result.errors[0].source_id == "missing"
    assert result.errors[0].error_type == "KeyError"


def test_collect_many_deduplicates_source_ids() -> None:
    manager = make_manager(ManagedStubSource("obsidian"))

    result = manager.collect_many(
        ("obsidian", "obsidian"),
        PerceptionRequest(),
    )

    assert result.requested_source_ids == ("obsidian",)
    assert len(result.signals) == 1


def test_collect_many_rejects_blank_source_ids() -> None:
    manager = make_manager()

    with pytest.raises(ValueError, match="cannot be blank"):
        manager.collect_many(("   ",), PerceptionRequest())


def test_collect_from_rejects_mismatched_batch_source() -> None:
    manager = make_manager(
        ManagedStubSource(
            "expected",
            returned_source_id="unexpected",
        )
    )

    with pytest.raises(ValueError, match="returned a batch"):
        manager.collect_from("expected", PerceptionRequest())


def test_collect_all_uses_registered_sources() -> None:
    manager = make_manager(
        ManagedStubSource("beta"),
        ManagedStubSource("alpha"),
    )

    result = manager.collect_all(PerceptionRequest())

    assert result.requested_source_ids == ("alpha", "beta")
    assert result.successful_source_ids == ("alpha", "beta")

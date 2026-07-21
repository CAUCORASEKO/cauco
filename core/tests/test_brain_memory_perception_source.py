from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cauco_core.memory import MemoryEngine, MemorySearch
from cauco_core.perception import (
    BRAIN_MEMORY_SOURCE_ID,
    BrainMemoryPerceptionSource,
    PerceptionCapability,
    PerceptionModality,
    PerceptionRequest,
    PerceptionSourceStatus,
)


def build_source(brain: Path) -> BrainMemoryPerceptionSource:
    engine = MemoryEngine(brain)
    search = MemorySearch(engine.memory_service)
    return BrainMemoryPerceptionSource(engine, search)


def write_memory(
    brain: Path,
    relative_path: str,
    content: str,
) -> Path:
    target = brain / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def test_source_exposes_stable_metadata(tmp_path: Path) -> None:
    source = build_source(tmp_path / "brain")

    assert source.metadata.source_id == BRAIN_MEMORY_SOURCE_ID
    assert source.supports(PerceptionCapability.READ)
    assert source.supports(PerceptionCapability.SEARCH)
    assert not source.supports(PerceptionCapability.WATCH)


def test_health_is_degraded_before_refresh(tmp_path: Path) -> None:
    source = build_source(tmp_path / "brain")

    health = source.health()

    assert health.status is PerceptionSourceStatus.DEGRADED
    assert health.message == "Brain memory has not been refreshed."


def test_collect_requires_refreshed_memory(tmp_path: Path) -> None:
    source = build_source(tmp_path / "brain")

    with pytest.raises(RuntimeError, match="must be refreshed"):
        source.collect(PerceptionRequest())


def test_read_collection_returns_memory_signals(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    write_memory(
        brain,
        "projects/aurora.md",
        "# Aurora\n\nDigital trust infrastructure.",
    )
    write_memory(
        brain,
        "tasks.md",
        "# Tasks\n\n- Continue Cauco perception.",
    )

    source = build_source(brain)
    source.memory_engine.refresh()

    batch = source.collect(PerceptionRequest())

    assert batch.source_id == BRAIN_MEMORY_SOURCE_ID
    assert len(batch.signals) == 2
    assert tuple(signal.reference for signal in batch.signals) == (
        "projects/aurora.md",
        "tasks.md",
    )
    assert all(
        signal.modality is PerceptionModality.FILE
        for signal in batch.signals
    )


def test_read_collection_respects_limit(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    write_memory(brain, "alpha.md", "# Alpha\n\nFirst.")
    write_memory(brain, "beta.md", "# Beta\n\nSecond.")

    source = build_source(brain)
    source.memory_engine.refresh()

    batch = source.collect(PerceptionRequest(limit=1))

    assert len(batch.signals) == 1
    assert batch.signals[0].reference == "alpha.md"


def test_search_collection_returns_ranked_excerpt(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    write_memory(
        brain,
        "projects/aurora.md",
        "# Aurora\n\nAurora provides digital trust infrastructure.",
    )
    write_memory(
        brain,
        "notes.md",
        "# Notes\n\nA brief reference to Aurora.",
    )

    source = build_source(brain)
    source.memory_engine.refresh()

    batch = source.collect(
        PerceptionRequest(
            query="Aurora digital trust",
            limit=5,
        )
    )

    assert len(batch.signals) == 2
    assert batch.signals[0].reference == "projects/aurora.md"
    assert "Aurora" in batch.signals[0].content
    assert batch.signals[0].metadata["score"] > 0
    assert "aurora" in batch.signals[0].metadata["matched_terms"]


def test_search_collection_respects_since_filter(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    write_memory(
        brain,
        "projects/old.md",
        "# Old Aurora\n\nAurora archive.",
    )

    source = build_source(brain)
    source.memory_engine.refresh()

    future = datetime.now(UTC) + timedelta(days=1)
    batch = source.collect(
        PerceptionRequest(
            query="Aurora",
            since=future,
        )
    )

    assert batch.signals == ()


def test_signal_ids_are_stable_across_collections(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    write_memory(
        brain,
        "projects/cauco.md",
        "# Cauco\n\nLocal cognitive system.",
    )

    source = build_source(brain)
    source.memory_engine.refresh()

    first = source.collect(PerceptionRequest())
    second = source.collect(PerceptionRequest())

    assert first.signals[0].signal_id == second.signals[0].signal_id


def test_health_is_available_after_refresh(tmp_path: Path) -> None:
    brain = tmp_path / "brain"
    write_memory(brain, "memory.md", "# Memory\n\nPersistent information.")

    source = build_source(brain)
    source.memory_engine.refresh()

    health = source.health()

    assert health.status is PerceptionSourceStatus.AVAILABLE
    assert health.message == "1 memory objects available."

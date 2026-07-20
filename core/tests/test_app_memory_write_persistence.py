from pathlib import Path

from fastapi.testclient import TestClient

from cauco_core.config import Settings
from cauco_core.main import create_app
from cauco_core.memory_writing.models import (
    MemoryWriteProposalState,
    MemoryWriteRequest,
)
from cauco_core.memory_writing.sqlite_store import (
    SQLiteMemoryWriteProposalStore,
)


def test_create_app_restores_memory_write_proposal_after_restart(
    tmp_path: Path,
) -> None:
    brain = tmp_path / "brain"
    brain.mkdir()
    database_path = tmp_path / "runtime" / "cauco.db"

    settings = Settings(
        brain_dir=brain,
        database_path=database_path,
    )

    first_app = create_app(settings)

    with TestClient(first_app):
        assert isinstance(
            first_app.state.memory_write_proposal_store,
            SQLiteMemoryWriteProposalStore,
        )
        assert first_app.state.database.path == database_path.resolve()

        proposal = first_app.state.memory_write_proposal_builder.build(
            MemoryWriteRequest(instruction="Add a task to verify application persistence")
        )
        created = first_app.state.memory_write_proposal_store.put(proposal)

        assert created.state is MemoryWriteProposalState.PENDING

    second_app = create_app(settings)

    with TestClient(second_app):
        assert isinstance(
            second_app.state.memory_write_proposal_store,
            SQLiteMemoryWriteProposalStore,
        )

        restored = second_app.state.memory_write_proposal_store.get(proposal.proposal_id)

        assert restored.proposal.proposal_id == proposal.proposal_id
        assert restored.proposal.model_dump() == proposal.model_dump()
        assert restored.state is MemoryWriteProposalState.PENDING
        assert restored.created_at == created.created_at
        assert restored.expires_at == created.expires_at
        assert restored.applied_at is None

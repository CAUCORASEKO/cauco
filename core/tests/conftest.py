from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cauco_core.config import Settings
from cauco_core.main import create_app


@pytest.fixture(autouse=True)
def isolated_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAUCO_DATABASE_PATH", str(tmp_path / "cauco-test.db"))


@pytest.fixture
def brain_dir(tmp_path: Path) -> Path:
    brain = tmp_path / "brain"
    brain.mkdir()
    return brain


@pytest.fixture
def client(brain_dir: Path) -> Iterator[TestClient]:
    with TestClient(create_app(Settings(brain_dir=brain_dir))) as test_client:
        yield test_client

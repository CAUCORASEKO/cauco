from pathlib import Path

from fastapi.testclient import TestClient

from cauco_core.config import Settings
from cauco_core.main import create_app


def perception_client(tmp_path: Path) -> tuple[TestClient, Path]:
    brain = tmp_path / "brain"
    brain.mkdir()

    (brain / "Projects.md").write_text(
        "# Projects\n\nCauco perception architecture.",
        encoding="utf-8",
    )
    (brain / "Tasks.md").write_text(
        "# Tasks\n\n- [ ] Integrate the perception API.",
        encoding="utf-8",
    )

    return TestClient(create_app(Settings(brain_dir=brain))), brain


def test_create_app_registers_brain_memory_perception_source(
    tmp_path: Path,
) -> None:
    client, _ = perception_client(tmp_path)

    with client:
        registry = client.app.state.perception_source_registry
        manager = client.app.state.perception_manager
        source = client.app.state.brain_memory_perception_source

        assert len(registry) == 1
        assert registry.get("brain_memory") is source
        assert manager.registry is registry


def test_list_and_read_perception_sources(tmp_path: Path) -> None:
    client, _ = perception_client(tmp_path)

    with client:
        response = client.get("/api/perception/sources")

        assert response.status_code == 200
        payload = response.json()
        assert payload["count"] == 1

        source = payload["sources"][0]
        assert source["metadata"]["source_id"] == "brain_memory"
        assert set(source["metadata"]["capabilities"]) == {"read", "search"}
        assert source["health"]["status"] == "available"

        detail = client.get("/api/perception/sources/brain_memory")
        assert detail.status_code == 200
        assert detail.json()["metadata"]["source_id"] == "brain_memory"

        health = client.get(
            "/api/perception/sources/brain_memory/health"
        )
        assert health.status_code == 200
        assert health.json()["status"] == "available"


def test_unknown_perception_source_returns_not_found(
    tmp_path: Path,
) -> None:
    client, _ = perception_client(tmp_path)

    with client:
        detail = client.get("/api/perception/sources/missing")
        health = client.get(
            "/api/perception/sources/missing/health"
        )

        assert detail.status_code == 404
        assert health.status_code == 404


def test_collects_read_signals_from_all_sources(tmp_path: Path) -> None:
    client, _ = perception_client(tmp_path)

    with client:
        response = client.post(
            "/api/perception/collect",
            json={"limit": 10},
        )

        assert response.status_code == 200
        payload = response.json()

        assert payload["requested_source_ids"] == ["brain_memory"]
        assert payload["successful_source_ids"] == ["brain_memory"]
        assert payload["errors"] == []
        assert len(payload["signals"]) == 2
        assert {
            signal["reference"]
            for signal in payload["signals"]
        } == {"Projects.md", "Tasks.md"}
        assert all(
            signal["source_id"] == "brain_memory"
            for signal in payload["signals"]
        )


def test_collects_search_signals(tmp_path: Path) -> None:
    client, _ = perception_client(tmp_path)

    with client:
        response = client.post(
            "/api/perception/collect",
            json={
                "source_ids": ["brain_memory"],
                "query": "perception",
                "limit": 10,
            },
        )

        assert response.status_code == 200
        payload = response.json()

        assert payload["successful_source_ids"] == ["brain_memory"]
        assert payload["errors"] == []
        assert len(payload["signals"]) >= 1
        assert any(
            signal["reference"] == "Projects.md"
            for signal in payload["signals"]
        )


def test_collect_reports_unknown_sources_without_losing_successes(
    tmp_path: Path,
) -> None:
    client, _ = perception_client(tmp_path)

    with client:
        response = client.post(
            "/api/perception/collect",
            json={
                "source_ids": [
                    "brain_memory",
                    "missing",
                    "brain_memory",
                ],
                "limit": 1,
            },
        )

        assert response.status_code == 200
        payload = response.json()

        assert payload["requested_source_ids"] == [
            "brain_memory",
            "missing",
        ]
        assert payload["successful_source_ids"] == ["brain_memory"]
        assert len(payload["signals"]) == 1
        assert len(payload["errors"]) == 1
        assert payload["errors"][0]["source_id"] == "missing"
        assert payload["errors"][0]["error_type"] == "KeyError"


def test_collect_rejects_invalid_payloads(tmp_path: Path) -> None:
    client, _ = perception_client(tmp_path)

    with client:
        blank_source = client.post(
            "/api/perception/collect",
            json={"source_ids": [" "]},
        )
        invalid_limit = client.post(
            "/api/perception/collect",
            json={"limit": 0},
        )
        extra_field = client.post(
            "/api/perception/collect",
            json={"unknown": True},
        )

        assert blank_source.status_code == 422
        assert invalid_limit.status_code == 422
        assert extra_field.status_code == 422

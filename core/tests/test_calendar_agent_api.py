from pathlib import Path

from fastapi.testclient import TestClient

from cauco_core.config import Settings
from cauco_core.main import create_app


def test_calendar_plan_api_exposes_questions_until_temporal_input_is_complete(
    tmp_path: Path,
) -> None:
    brain = tmp_path / "brain"
    brain.mkdir()
    with TestClient(create_app(Settings(brain_dir=brain))) as client:
        ambiguous = client.post(
            "/api/agents/calendar/plan",
            json={"instruction": "Crea un evento mañana a las 10"},
        )
        resolved = client.post(
            "/api/agents/calendar/plan",
            json={
                "instruction": (
                    'Crea un evento "Planificación" mañana a las 10 durante 60 minutos'
                ),
                "timezone": "Europe/Helsinki",
                "calendar_reference": "calendar_abcdefgh",
            },
        )

    assert ambiguous.status_code == 200
    assert ambiguous.json()["plan"]["steps"] == []
    assert ambiguous.json()["plan"]["open_questions"]
    assert ambiguous.json()["readiness"]["ready"] is False

    assert resolved.status_code == 200
    operations = [
        step["tool_reference"]["operation_id"] for step in resolved.json()["plan"]["steps"]
    ]
    assert operations == ["list_events", "create_event"]
    assert resolved.json()["readiness"]["ready"] is True
    mutation = next(
        item
        for item in resolved.json()["readiness"]["references"]
        if item["operation_id"] == "create_event"
    )
    assert mutation["preview_required"] is True
    assert mutation["executable_now"] is False

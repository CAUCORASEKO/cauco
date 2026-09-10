import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cauco_core.ai.ollama import OllamaProvider
from cauco_core.config import Settings
from cauco_core.main import create_app

ALL_MEMORY = {
    "Bienvenido.md": "# Bienvenido\nIDENTITY CONTENT",
    "Projects.md": "# Projects\nPROJECT CONTENT. Current project work.",
    "Tasks.md": "# Tasks\nTASK CONTENT. Today's work is prioritized.",
    "Decisions.md": "# Decisions\nDECISION CONTENT. We are using Obsidian.",
    "Relationships.md": "# Relationships\nRELATIONSHIP CONTENT. Ville is a collaborator.",
    "Memory Rules.md": "# Memory Rules\nRULE CONTENT",
}


@contextmanager
def integration_client(
    brain_files: dict[str, str] | None = None,
    *,
    timeout: bool = False,
) -> Iterator[tuple[TestClient, FastAPI, Path, dict[str, object]]]:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        if timeout:
            raise httpx.ReadTimeout("private timeout", request=request)
        return httpx.Response(
            200,
            json={
                "model": "llama3.1:latest",
                "message": {"role": "assistant", "content": "ok"},
            },
            request=request,
        )

    with TemporaryDirectory() as temporary_directory:
        brain = Path(temporary_directory) / "brain"
        brain.mkdir()
        for relative_path, content in (brain_files or {}).items():
            (brain / relative_path).write_text(content, encoding="utf-8")
        settings = Settings(brain_dir=brain)
        provider = OllamaProvider(
            base_url=settings.ollama_base_url,
            default_model=settings.default_model,
            timeout=settings.ai_request_timeout,
            temperature=settings.ai_temperature,
            max_output_tokens=settings.ai_max_output_tokens,
            http_client=httpx.Client(
                transport=httpx.MockTransport(handler),
                base_url=settings.ollama_base_url,
            ),
        )
        app = create_app(settings, ai_provider=provider)
        with TestClient(app) as client:
            yield client, app, brain, captured


@pytest.mark.parametrize(
    ("question", "intent", "sources", "included", "excluded"),
    [
        (
            "What should I work on today?",
            "planning",
            ["Projects.md", "Tasks.md"],
            ["PROJECT CONTENT", "TASK CONTENT"],
            ["DECISION CONTENT", "RELATIONSHIP CONTENT"],
        ),
        (
            "Why are we using Obsidian?",
            "decision",
            ["Decisions.md"],
            ["DECISION CONTENT"],
            ["TASK CONTENT", "RELATIONSHIP CONTENT"],
        ),
        (
            "What projects am I working on?",
            "project",
            ["Projects.md"],
            ["PROJECT CONTENT"],
            ["DECISION CONTENT", "RELATIONSHIP CONTENT"],
        ),
        (
            "Who is Ville?",
            "relationship",
            ["Relationships.md"],
            ["RELATIONSHIP CONTENT"],
            ["PROJECT CONTENT", "TASK CONTENT", "DECISION CONTENT"],
        ),
    ],
)
def test_chat_uses_only_deterministically_selected_memory(
    question: str,
    intent: str,
    sources: list[str],
    included: list[str],
    excluded: list[str],
) -> None:
    with integration_client(ALL_MEMORY) as (client, _, _, captured):
        response = client.post("/api/ai/chat", json={"message": question})

    assert response.status_code == 200
    assert response.json()["memory_sources"] == sources
    prompt = captured["messages"][1]["content"]  # type: ignore[index]
    assert f"Detected intent: {intent}" in prompt
    assert "Selection reasoning:" in prompt
    for content in included:
        assert content in prompt
    for content in excluded:
        assert content not in prompt


def test_full_content_is_read_only_for_selected_registry_objects() -> None:
    with integration_client(ALL_MEMORY) as (client, app, _, _):
        original_read = app.state.memory_service.read_file
        read_spy = Mock(wraps=original_read)
        app.state.memory_service.read_file = read_spy
        response = client.post(
            "/api/ai/chat",
            json={"message": "What should I work on today?"},
        )

    assert response.status_code == 200
    # Search reads the registry to determine relevance; only matching memory is
    # included in the prompt returned to the model.
    assert response.json()["memory_sources"] == ["Projects.md", "Tasks.md"]


def test_context_chat_response_contract_remains_unchanged() -> None:
    with integration_client(ALL_MEMORY) as (client, _, _, _):
        response = client.post("/api/ai/chat", json={"message": "Who is Ville?"})
    assert response.json() == {
        "provider": "ollama",
        "model": "llama3.1:latest",
        "response": "ok",
        "used_memory": True,
        "memory_sources": ["Relationships.md"],
        "used_tools": [],
        "used_agents": [],
    }


def test_empty_brain_uses_plain_question() -> None:
    with integration_client() as (client, _, _, captured):
        response = client.post("/api/ai/chat", json={"message": "Who is Ville?"})
    assert response.status_code == 200
    assert response.json()["used_memory"] is False
    assert captured["messages"][1]["content"] == "Who is Ville?"  # type: ignore[index]


def test_general_chat_with_unrelated_memory_uses_plain_question() -> None:
    question = "Can you suggest a recipe?"
    with integration_client(
        {"Projects.md": "# Projects\nAtlas migration is scheduled."}
    ) as (client, _, _, captured):
        response = client.post("/api/ai/chat", json={"message": question})

    assert response.status_code == 200
    assert response.json()["used_memory"] is False
    assert response.json()["memory_sources"] == []
    assert captured["messages"][1]["content"] == question  # type: ignore[index]


def test_general_intent_does_not_inject_unrelated_general_memory() -> None:
    with integration_client({"note.md": "# Note\nGENERAL CONTENT"}) as (
        client,
        _,
        _,
        captured,
    ):
        response = client.post("/api/ai/chat", json={"message": "Please explain this"})
    assert response.json()["memory_sources"] == []
    assert captured["messages"][1]["content"] == "Please explain this"  # type: ignore[index]


def test_context_builder_failure_uses_legacy_search_fallback() -> None:
    class BrokenContextBuilder:
        def build(self, question: str) -> None:
            raise RuntimeError(f"failed to analyze {question}")

    files = {"Projects.md": "# Projects\nProject Atlas is active."}
    with integration_client(files) as (client, app, _, captured):
        app.state.ai_service.context_builder = BrokenContextBuilder()
        response = client.post("/api/ai/chat", json={"message": "Project Atlas"})
    assert response.status_code == 200
    assert response.json()["memory_sources"] == ["Projects.md"]
    assert "Project Atlas is active." in captured["messages"][1]["content"]  # type: ignore[index]


def test_unreadable_selected_files_do_not_crash_chat() -> None:
    files = {"Projects.md": "# Projects\nProject", "Tasks.md": "# Tasks\nTask"}
    with integration_client(files) as (client, _, brain, captured):
        (brain / "Projects.md").write_bytes(b"\xff\xfe")
        (brain / "Tasks.md").write_bytes(b"\xff\xfe")
        response = client.post(
            "/api/ai/chat",
            json={"message": "What should I work on today?"},
        )
    assert response.status_code == 200
    assert response.json()["memory_sources"] == []
    assert captured["messages"][1]["content"] == "What should I work on today?"  # type: ignore[index]


def test_ollama_error_behavior_is_preserved_with_selected_context() -> None:
    with integration_client(ALL_MEMORY, timeout=True) as (client, _, _, _):
        response = client.post(
            "/api/ai/chat",
            json={"message": "What should I work on today?"},
        )
    assert response.status_code == 504
    assert response.json() == {"detail": "The local AI provider timed out."}

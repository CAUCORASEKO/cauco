import sys

import pytest
from cauco_reasoning import DeepAgentsReasoningEngine, NoOpReasoningEngine
from pydantic import ValidationError

from cauco_core.config import Settings
from cauco_core.main import create_app
from cauco_core.reasoning import build_reasoning_engine


def test_default_settings_build_noop_engine() -> None:
    settings = Settings()

    engine = build_reasoning_engine(settings)

    assert settings.reasoning_enabled is False
    assert settings.reasoning_provider == "noop"
    assert isinstance(engine, NoOpReasoningEngine)


def test_disabled_reasoning_always_builds_noop() -> None:
    settings = Settings(
        reasoning_enabled=False,
        reasoning_provider="deepagents",
        reasoning_model="openai:test-model",
    )

    assert isinstance(build_reasoning_engine(settings), NoOpReasoningEngine)


def test_enabled_noop_provider_builds_noop() -> None:
    settings = Settings(reasoning_enabled=True, reasoning_provider="noop")

    assert isinstance(build_reasoning_engine(settings), NoOpReasoningEngine)


def test_enabled_deepagents_builds_configured_engine_without_live_call() -> None:
    settings = Settings(
        reasoning_enabled=True,
        reasoning_provider="deepagents",
        reasoning_model="openai:test-model",
    )

    imported_before = sys.modules.get("deepagents")
    engine = build_reasoning_engine(settings)

    assert isinstance(engine, DeepAgentsReasoningEngine)
    assert engine.model == "openai:test-model"
    assert sys.modules.get("deepagents") is imported_before


@pytest.mark.parametrize("model", [None, "   "])
def test_enabled_deepagents_without_model_fails_closed(model: str | None) -> None:
    settings = Settings(
        reasoning_enabled=True,
        reasoning_provider="deepagents",
        reasoning_model=model,
    )

    with pytest.raises(ValueError, match="requires an explicit model"):
        build_reasoning_engine(settings)
    with pytest.raises(ValueError, match="requires an explicit model"):
        create_app(settings)


def test_unsupported_reasoning_provider_is_rejected() -> None:
    with pytest.raises(ValidationError, match="Unsupported reasoning provider"):
        Settings(reasoning_provider="unknown")


def test_deepagents_bootstrap_exposes_no_cauco_execution_objects() -> None:
    app = create_app(
        Settings(
            reasoning_enabled=True,
            reasoning_provider="deepagents",
            reasoning_model="openai:test-model",
        )
    )
    engine = app.state.reasoning_service.engine

    assert isinstance(engine, DeepAgentsReasoningEngine)
    assert not hasattr(engine, "execution_service")
    assert not hasattr(engine, "mutation_service")
    assert not hasattr(engine, "task_runtime")
    assert not hasattr(engine, "tool_registry")

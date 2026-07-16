import pytest
from pydantic import ValidationError

from cauco_core.config import Settings


def test_ai_configuration_defaults() -> None:
    settings = Settings()
    assert settings.ai_provider == "ollama"
    assert settings.ollama_base_url == "http://127.0.0.1:11434"
    assert settings.default_model == "llama3.1:latest"
    assert settings.ai_temperature == 0.1


def test_ai_configuration_supports_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAUCO_DEFAULT_MODEL", "qwen2.5-coder:7b")
    monkeypatch.setenv("CAUCO_AI_REQUEST_TIMEOUT", "90")
    monkeypatch.setenv("CAUCO_AI_MAX_OUTPUT_TOKENS", "2048")
    settings = Settings()
    assert settings.default_model == "qwen2.5-coder:7b"
    assert settings.ai_request_timeout == 90
    assert settings.ai_max_output_tokens == 2048


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:11434",
        "http://example.com:11434",
        "http://127.0.0.1:11434/untrusted-path",
    ],
)
def test_ollama_url_rejects_non_local_or_extended_addresses(url: str) -> None:
    with pytest.raises(ValidationError, match="Ollama base URL"):
        Settings(ollama_base_url=url)

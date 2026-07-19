from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def default_brain_directory() -> Path:
    """Return the repository's portable development brain template."""
    return Path(__file__).resolve().parents[3] / "brain-template"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CAUCO_", extra="ignore")

    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1, le=65535)
    brain_dir: Path = Field(default_factory=default_brain_directory)
    memory_max_file_size: int = Field(default=524_288, ge=1024, le=10_485_760)
    memory_context_max_files: int = Field(default=3, ge=1, le=10)
    memory_context_max_characters: int = Field(default=6000, ge=500, le=50_000)
    memory_write_proposal_ttl_seconds: int = Field(default=1800, ge=60, le=86_400)
    agent_plan_review_ttl_seconds: int = Field(default=1800, ge=60, le=86_400)
    agent_plan_review_max_records: int = Field(default=100, ge=1, le=10_000)
    workspace_dir: Path | None = None
    execution_max_records: int = Field(default=100, ge=1, le=10_000)
    execution_max_file_bytes: int = Field(default=1_000_000, ge=1024, le=10_000_000)
    ai_provider: str = "ollama"
    ollama_base_url: str = "http://127.0.0.1:11434"
    default_model: str = "llama3.1:latest"
    ai_request_timeout: float = Field(default=60.0, gt=0, le=600)
    ai_temperature: float | None = Field(default=0.1, ge=0, le=2)
    ai_max_output_tokens: int | None = Field(default=1024, ge=1, le=32768)

    @field_validator("ai_provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized != "ollama":
            raise ValueError("Only the local Ollama provider is currently supported.")
        return normalized

    @field_validator("ollama_base_url")
    @classmethod
    def validate_ollama_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        parsed = urlparse(normalized)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Ollama base URL must be a local HTTP address.")
        if (
            parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Ollama base URL must not include credentials, a path, or parameters.")
        return normalized

    @field_validator("default_model")
    @classmethod
    def validate_default_model(cls, value: str) -> str:
        from cauco_core.ai.base import validate_model_name

        return validate_model_name(value)

    def resolved_brain_dir(self) -> Path:
        return self.brain_dir.expanduser().resolve()

    def resolved_workspace_dir(self) -> Path | None:
        return self.workspace_dir.expanduser().resolve() if self.workspace_dir else None

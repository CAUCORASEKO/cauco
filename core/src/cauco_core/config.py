from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def default_brain_directory() -> Path:
    """Return the repository's portable development brain template."""
    return Path(__file__).resolve().parents[3] / "brain-template"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CAUCO_", extra="ignore")

    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1, le=65535)
    brain_dir: Path = Field(default_factory=default_brain_directory)

    def resolved_brain_dir(self) -> Path:
        return self.brain_dir.expanduser().resolve()

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

MODEL_NAME_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*"
    r"(?:/[A-Za-z0-9][A-Za-z0-9._-]*)*"
    r"(?::[A-Za-z0-9][A-Za-z0-9._-]*)?$"
)
MAX_MODEL_NAME_LENGTH = 128


def validate_model_name(value: str) -> str:
    model = value.strip()
    if (
        not model
        or len(model) > MAX_MODEL_NAME_LENGTH
        or ".." in model
        or not MODEL_NAME_PATTERN.fullmatch(model)
    ):
        raise ValueError("Model name contains unsupported characters.")
    return model


@dataclass(frozen=True, slots=True)
class AIProviderMetadata:
    name: str
    base_url: str
    default_model: str


@dataclass(frozen=True, slots=True)
class AIModel:
    name: str
    size: int
    parameter_size: str | None = None
    quantization_level: str | None = None


class AIProvider(ABC):
    metadata: AIProviderMetadata

    @abstractmethod
    def is_available(self) -> bool:
        """Return whether the local provider responds with a valid model list."""

    @abstractmethod
    def list_models(self) -> list[AIModel]:
        """Return installed models reported by the provider."""

    @abstractmethod
    def chat(self, message: str, model: str, system_prompt: str) -> str:
        """Return one non-streaming assistant response."""

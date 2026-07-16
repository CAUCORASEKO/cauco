from dataclasses import dataclass

from cauco_core.ai.base import AIModel, AIProvider, validate_model_name
from cauco_core.ai.exceptions import ProviderTimeoutError, ProviderUnavailableError
from cauco_core.ai.prompt import CAUCO_SYSTEM_PROMPT


@dataclass(frozen=True, slots=True)
class AIStatus:
    provider: str
    available: bool
    base_url: str
    default_model: str
    default_model_installed: bool
    models_count: int


@dataclass(frozen=True, slots=True)
class AIChatResult:
    provider: str
    model: str
    response: str


class AIService:
    def __init__(self, provider: AIProvider) -> None:
        self.provider = provider

    def status(self) -> AIStatus:
        metadata = self.provider.metadata
        try:
            models = self.provider.list_models()
        except (ProviderUnavailableError, ProviderTimeoutError):
            return AIStatus(
                provider=metadata.name,
                available=False,
                base_url=metadata.base_url,
                default_model=metadata.default_model,
                default_model_installed=False,
                models_count=0,
            )
        model_names = {model.name for model in models}
        return AIStatus(
            provider=metadata.name,
            available=True,
            base_url=metadata.base_url,
            default_model=metadata.default_model,
            default_model_installed=metadata.default_model in model_names,
            models_count=len(models),
        )

    def list_models(self) -> list[AIModel]:
        return self.provider.list_models()

    def chat(self, message: str, model: str | None = None) -> AIChatResult:
        selected_model = validate_model_name(model or self.provider.metadata.default_model)
        response = self.provider.chat(message, selected_model, CAUCO_SYSTEM_PROMPT)
        return AIChatResult(
            provider=self.provider.metadata.name,
            model=selected_model,
            response=response,
        )

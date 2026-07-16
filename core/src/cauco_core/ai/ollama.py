from typing import Any

import httpx

from cauco_core.ai.base import AIModel, AIProvider, AIProviderMetadata, validate_model_name
from cauco_core.ai.exceptions import (
    MalformedProviderResponseError,
    ModelNotFoundError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)


class OllamaProvider(AIProvider):
    def __init__(
        self,
        *,
        base_url: str,
        default_model: str,
        timeout: float,
        temperature: float | None,
        max_output_tokens: int | None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.metadata = AIProviderMetadata(
            name="ollama", base_url=base_url, default_model=validate_model_name(default_model)
        )
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self._client = http_client or httpx.Client(base_url=base_url, timeout=timeout)

    def is_available(self) -> bool:
        try:
            self.list_models()
        except (ProviderUnavailableError, ProviderTimeoutError):
            return False
        return True

    def list_models(self) -> list[AIModel]:
        response = self._request("GET", "/api/tags")
        payload = self._json_object(response)
        raw_models = payload.get("models")
        if not isinstance(raw_models, list):
            raise MalformedProviderResponseError("Ollama returned an invalid model list.")

        models: list[AIModel] = []
        for raw_model in raw_models:
            if not isinstance(raw_model, dict):
                raise MalformedProviderResponseError("Ollama returned invalid model metadata.")
            name = raw_model.get("name")
            size = raw_model.get("size")
            details = raw_model.get("details", {})
            if not isinstance(name, str) or not isinstance(size, int) or size < 0:
                raise MalformedProviderResponseError("Ollama returned invalid model metadata.")
            if not isinstance(details, dict):
                details = {}
            parameter_size = self._optional_string(details.get("parameter_size"))
            quantization = self._optional_string(details.get("quantization_level"))
            try:
                safe_name = validate_model_name(name)
            except ValueError as error:
                raise MalformedProviderResponseError(
                    "Ollama returned an invalid model name."
                ) from error
            models.append(
                AIModel(
                    name=safe_name,
                    size=size,
                    parameter_size=parameter_size,
                    quantization_level=quantization,
                )
            )
        return sorted(models, key=lambda item: item.name.casefold())

    def chat(self, message: str, model: str, system_prompt: str) -> str:
        selected_model = validate_model_name(model)
        options: dict[str, float | int] = {}
        if self.temperature is not None:
            options["temperature"] = self.temperature
        if self.max_output_tokens is not None:
            options["num_predict"] = self.max_output_tokens
        payload: dict[str, Any] = {
            "model": selected_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
            "stream": False,
        }
        if options:
            payload["options"] = options

        response = self._request("POST", "/api/chat", json=payload)
        data = self._json_object(response)
        response_model = data.get("model")
        assistant_message = data.get("message")
        if response_model is not None and response_model != selected_model:
            raise MalformedProviderResponseError("Ollama returned a response for another model.")
        if not isinstance(assistant_message, dict):
            raise MalformedProviderResponseError("Ollama returned an invalid chat response.")
        role = assistant_message.get("role")
        content = assistant_message.get("content")
        if role != "assistant" or not isinstance(content, str) or not content.strip():
            raise MalformedProviderResponseError("Ollama returned an invalid chat response.")
        return content.strip()

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as error:
            raise ProviderTimeoutError("The local AI provider timed out.") from error
        except httpx.RequestError as error:
            raise ProviderUnavailableError("The local AI provider is unavailable.") from error
        if response.status_code == 404:
            raise ModelNotFoundError("The requested Ollama model is not installed.")
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise ProviderUnavailableError("The local AI provider request failed.") from error
        return response

    @staticmethod
    def _json_object(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as error:
            raise MalformedProviderResponseError("Ollama returned invalid JSON.") from error
        if not isinstance(payload, dict):
            raise MalformedProviderResponseError("Ollama returned an invalid response.")
        return payload

    @staticmethod
    def _optional_string(value: object) -> str | None:
        return value if isinstance(value, str) and value else None

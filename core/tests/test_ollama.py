import json

import httpx
import pytest

from cauco_core.ai.exceptions import (
    MalformedProviderResponseError,
    ModelNotFoundError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from cauco_core.ai.ollama import OllamaProvider
from cauco_core.ai.prompt import CAUCO_SYSTEM_PROMPT


def provider(handler: httpx.MockTransport) -> OllamaProvider:
    client = httpx.Client(transport=handler, base_url="http://127.0.0.1:11434")
    return OllamaProvider(
        base_url="http://127.0.0.1:11434",
        default_model="llama3.1:latest",
        timeout=10,
        temperature=0.1,
        max_output_tokens=512,
        http_client=client,
    )


def test_ollama_available() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"models": []}, request=request)
    )
    assert provider(transport).is_available() is True


def test_ollama_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    ollama = provider(httpx.MockTransport(handler))
    assert ollama.is_available() is False
    with pytest.raises(ProviderUnavailableError, match="unavailable"):
        ollama.list_models()


def test_installed_model_listing() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "qwen2.5-coder:7b",
                        "size": 4_700_000_000,
                        "details": {
                            "parameter_size": "7.6B",
                            "quantization_level": "Q4_K_M",
                        },
                    }
                ]
            },
            request=request,
        )
    )
    assert provider(transport).list_models()[0].name == "qwen2.5-coder:7b"
    assert provider(transport).list_models()[0].parameter_size == "7.6B"


def test_successful_non_streaming_chat_uses_controlled_payload() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "llama3.1:latest",
                "message": {"role": "assistant", "content": "Cauco coordinates work."},
            },
            request=request,
        )

    response = provider(httpx.MockTransport(handler)).chat(
        "What is Cauco?", "llama3.1:latest", CAUCO_SYSTEM_PROMPT
    )
    assert response == "Cauco coordinates work."
    assert captured["stream"] is False
    assert captured["messages"] == [
        {"role": "system", "content": CAUCO_SYSTEM_PROMPT},
        {"role": "user", "content": "What is Cauco?"},
    ]
    assert captured["options"] == {"temperature": 0.1, "num_predict": 512}


def test_model_not_found() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(404, json={"error": "not found"}, request=request)
    )
    with pytest.raises(ModelNotFoundError, match="not installed"):
        provider(transport).chat("Hello", "missing:latest", CAUCO_SYSTEM_PROMPT)


def test_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ProviderTimeoutError, match="timed out"):
        provider(httpx.MockTransport(handler)).list_models()


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not-json"),
        httpx.Response(200, json={"unexpected": []}),
        httpx.Response(200, json={"models": [{"name": 42, "size": "large"}]}),
    ],
)
def test_malformed_model_response(response: httpx.Response) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        response.request = request
        return response

    with pytest.raises(MalformedProviderResponseError):
        provider(httpx.MockTransport(handler)).list_models()


def test_malformed_chat_response() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, json={"message": {"role": "assistant"}}, request=request
        )
    )
    with pytest.raises(MalformedProviderResponseError, match="invalid chat"):
        provider(transport).chat("Hello", "llama3.1:latest", CAUCO_SYSTEM_PROMPT)

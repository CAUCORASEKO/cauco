class AIProviderError(RuntimeError):
    """Base error for safe provider failures."""


class ProviderUnavailableError(AIProviderError):
    """Raised when the configured local provider cannot be reached."""


class ProviderTimeoutError(AIProviderError):
    """Raised when a provider request exceeds its configured timeout."""


class ModelNotFoundError(AIProviderError):
    """Raised when the requested model is not installed."""


class MalformedProviderResponseError(AIProviderError):
    """Raised when a provider returns an unexpected payload."""

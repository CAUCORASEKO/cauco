"""Provider-independent local AI integration."""

from cauco_core.ai.base import AIModel, AIProvider, AIProviderMetadata
from cauco_core.ai.service import AIService

__all__ = ["AIModel", "AIProvider", "AIProviderMetadata", "AIService"]

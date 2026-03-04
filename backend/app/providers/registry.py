"""Provider registry — factory for provider instances."""

from app.providers.anthropic import AnthropicProvider
from app.providers.base import BaseProvider
from app.providers.google import GoogleVertexProvider
from app.providers.openai import OpenAIProvider

_PROVIDERS: dict[str, BaseProvider] = {
    "anthropic": AnthropicProvider(),
    "openai": OpenAIProvider(),
    "google": GoogleVertexProvider(),
}


def get_provider(provider_type: str) -> BaseProvider | None:
    return _PROVIDERS.get(provider_type)

"""One small interface over the LLM provider, so switching provider is a one-file change."""

from functools import lru_cache
from typing import Protocol

from app.config import get_settings


class LLMClient(Protocol):
    def complete(self, system: str, user: str, *, model: str | None = None) -> str: ...


class AnthropicClient:
    """Calls the Anthropic Messages API directly (used until Bedrock access is approved)."""

    def __init__(self, api_key: str, default_model: str, max_tokens: int = 1024) -> None:
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)
        self._default_model = default_model
        self._max_tokens = max_tokens

    def complete(self, system: str, user: str, *, model: str | None = None) -> str:
        response = self._client.messages.create(
            model=model or self._default_model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        # The reply is a list of content blocks; join the text ones.
        return "".join(block.text for block in response.content if block.type == "text")


@lru_cache
def get_llm_client() -> LLMClient:
    """Return a client for settings.llm_provider. Bedrock comes later as a second provider."""
    settings = get_settings()
    if settings.llm_provider == "anthropic":
        if not settings.anthropic_api_key:
            raise RuntimeError("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set in .env")
        return AnthropicClient(settings.anthropic_api_key, settings.llm_model_small)
    raise NotImplementedError(f"LLM provider {settings.llm_provider!r} is not implemented yet")

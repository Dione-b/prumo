from __future__ import annotations

from typing import Protocol, TypeVar

T = TypeVar("T")


class CacheProvider(Protocol):
    """
    Zero-cost abstraction for LLM context caching.

    Structural protocol only used at type-check time (no runtime overhead).
    Allows swapping Google GenAI for other providers without touching
    orchestrators or business logic.
    """

    async def count_tokens(self, text: str, model: str) -> int:
        """
        Return the total token count for the given text and model.
        """

    async def create_cached_content(self, content: str, model: str, ttl: int) -> str:
        """
        Create an explicit cached content object and return its cache name.
        """

    async def generate_with_cache(
        self,
        cache_name: str,
        prompt: str,
        schema: type[T],
        model: str = "",
        system_instruction: str | None = None,
    ) -> T:
        """
        Generate a structured response using an existing cached content name.
        """

    async def generate_text(
        self,
        prompt: str,
        system_instruction: str = "",
        model: str = "",
        temperature: float = 0.2,
        cache_name: str | None = None,
    ) -> str:
        """
        Generate free-form text (e.g. YAML) with optional cached context.
        """

"""Gemini Client Wrapper for Google GenAI SDK (2026)."""

from __future__ import annotations

import asyncio
import json
from typing import TypeVar

import structlog
from google import genai
from google.genai.types import CreateCachedContentConfig

from app.config import settings

logger = structlog.get_logger()
T = TypeVar("T")


class GeminiClient:
    """Wrapper for 2026 SDK with thread safety (C_02)."""

    def __init__(self) -> None:
        self._client = genai.Client(api_key=settings.gemini_api_key.get_secret_value())

    async def count_tokens(self, text: str, model: str) -> int:
        """Count tokens via model's tokenizer in to_thread."""

        def sync_count_tokens() -> int:
            response = self._client.models.count_tokens(
                model=model,
                contents=text,
            )
            return int(response.total_tokens or 0)

        return await asyncio.to_thread(sync_count_tokens)

    async def create_cached_content(self, content: str, model: str, ttl: int) -> str:
        """caches.create with CreateCachedContentConfig in to_thread."""

        def sync_create_cached_content() -> str:
            config = CreateCachedContentConfig(
                ttl=f"{ttl}s",
                system_instruction=(
                    "You are a strict technical context orchestrator. "
                    "Answer questions based strictly on the provided document. "
                    "If the answer is not in the document, you must say 'I don't know'."
                ),
                contents=[content],
            )
            cache = self._client.caches.create(
                model=model,
                config=config,
            )
            return str(cache.name)

        return await asyncio.to_thread(sync_create_cached_content)

    async def generate_with_cache(
        self,
        cache_name: str,
        prompt: str,
        schema: type[T],
        model: str = "",
        system_instruction: str | None = None,
    ) -> T:
        """Call generate_content with a cached content name."""
        resolved_model = model or settings.gemini_synthesis_model

        def sync_call() -> str:
            config = genai.types.GenerateContentConfig(
                cached_content=cache_name,
                response_mime_type="application/json",
                response_schema=schema,
                temperature=0.0,
            )
            # Add system_instruction only if present to avoid cache conflicts
            if system_instruction:
                config.system_instruction = system_instruction

            response = self._client.models.generate_content(
                model=resolved_model,
                contents=prompt,
                config=config,
            )
            return str(response.text)

        result_text = await asyncio.to_thread(sync_call)
        from pydantic import BaseModel

        if issubclass(schema, BaseModel):
            return schema.model_validate_json(result_text)  # type: ignore[no-any-return, return-value]
        return json.loads(result_text)  # type: ignore[no-any-return]

    async def generate_text(
        self,
        prompt: str,
        system_instruction: str = "",
        model: str = "",
        temperature: float = 0.2,
        cache_name: str | None = None,
    ) -> str:
        """Generate free-form text (e.g. YAML) via Gemini in to_thread (C_02)."""
        resolved_model = model or settings.gemini_synthesis_model

        def sync_call() -> str:
            config = genai.types.GenerateContentConfig(
                temperature=temperature,
                system_instruction=system_instruction or None,
            )
            if cache_name:
                config.cached_content = cache_name

            response = self._client.models.generate_content(
                model=resolved_model,
                contents=prompt,
                config=config,
            )
            return str(response.text)

        return await asyncio.to_thread(sync_call)

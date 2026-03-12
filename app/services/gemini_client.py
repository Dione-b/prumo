# Copyright (C) 2026 Dione Bastos
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.


"""Gemini Client — unified wrapper for Google GenAI SDK (2026).

Provides embed, generate_text, generate_structured, and cache operations.
All sync SDK calls run in threads via asyncio.to_thread to keep the
event loop unblocked.
"""

from __future__ import annotations

import asyncio
import json
from typing import TypeVar

import structlog
from google import genai
from google.genai.types import CreateCachedContentConfig
from pydantic import BaseModel

from app.config import settings

logger = structlog.get_logger()
T = TypeVar("T")


class GeminiClient:
    """Unified Gemini client with thread-safe sync calls."""

    def __init__(self) -> None:
        self._client = genai.Client(api_key=settings.gemini_api_key.get_secret_value())

    # ── Embedding ─────────────────────────────────────────────────────────

    async def embed(self, text: str) -> list[float]:
        """Embed a single text using Gemini text-embedding-004."""

        def sync_embed() -> list[float]:
            response = self._client.models.embed_content(
                model=settings.gemini_embedding_model,
                contents=text,
            )
            return [float(v) for v in response.embeddings[0].values]

        return await asyncio.to_thread(sync_embed)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts sequentially to respect rate limits."""
        embeddings: list[list[float]] = []
        for text in texts:
            embedding = await self.embed(text)
            embeddings.append(embedding)
        return embeddings

    # ── Structured Generation ─────────────────────────────────────────────

    async def generate_structured(
        self,
        prompt: str,
        response_model: type[T],
        *,
        model: str = "",
        system_instruction: str = "",
        temperature: float | None = None,
    ) -> T:
        """Generate structured output matching a Pydantic schema.

        Uses Gemini's native response_schema for guaranteed JSON compliance.
        Defaults to Flash model for cost efficiency.
        """
        resolved_model = model or settings.gemini_flash_model
        resolved_temp = temperature if temperature is not None else settings.gemini_temperature

        def sync_call() -> str:
            config = genai.types.GenerateContentConfig(
                temperature=resolved_temp,
                response_mime_type="application/json",
                response_schema=response_model,
            )
            if system_instruction:
                config.system_instruction = system_instruction

            response = self._client.models.generate_content(
                model=resolved_model,
                contents=prompt,
                config=config,
            )
            return str(response.text)

        result_text = await asyncio.to_thread(sync_call)

        if isinstance(response_model, type) and issubclass(response_model, BaseModel):
            return response_model.model_validate_json(result_text)  # type: ignore[return-value]
        return json.loads(result_text)  # type: ignore[return-value]

    # ── Free-form Text Generation ─────────────────────────────────────────

    async def generate_text(
        self,
        prompt: str,
        system_instruction: str = "",
        model: str = "",
        temperature: float = 0.2,
        cache_name: str | None = None,
    ) -> str:
        """Generate free-form text via Gemini in to_thread."""
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

    # ── Token Counting ────────────────────────────────────────────────────

    async def count_tokens(self, text: str, model: str) -> int:
        """Count tokens via model's tokenizer in to_thread."""

        def sync_count_tokens() -> int:
            response = self._client.models.count_tokens(
                model=model,
                contents=text,
            )
            return int(response.total_tokens or 0)

        return await asyncio.to_thread(sync_count_tokens)

    # ── Caching ───────────────────────────────────────────────────────────

    async def create_cached_content(self, content: str, model: str, ttl: int) -> str:
        """Create an explicit cache with CreateCachedContentConfig."""

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
            if system_instruction:
                config.system_instruction = system_instruction

            response = self._client.models.generate_content(
                model=resolved_model,
                contents=prompt,
                config=config,
            )
            return str(response.text)

        result_text = await asyncio.to_thread(sync_call)

        if isinstance(schema, type) and issubclass(schema, BaseModel):
            return schema.model_validate_json(result_text)  # type: ignore[return-value]
        return json.loads(result_text)  # type: ignore[return-value]

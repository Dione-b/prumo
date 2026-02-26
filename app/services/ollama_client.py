"""OllamaClient — centralized local model access."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from ollama import AsyncClient

from app.config import settings

logger = structlog.get_logger()

# Use a global semaphore to ensure strictly sequential local model execution
_global_semaphore = asyncio.Semaphore(settings.ollama_max_concurrent)


class OllamaClient:
    """Centralizes local model access. Enforces OLLAMA_KEEP_ALIVE=0
    and uses a global asyncio.Semaphore to prevent VRAM overlap.
    """

    def __init__(self) -> None:
        self._global_semaphore = _global_semaphore
        self._client = AsyncClient(host=settings.ollama_base_url)

    async def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        think: bool = True,
        options: dict[str, Any] | None = None,
    ) -> Any:
        """Sends a chat request with thinking and tool support."""
        try:
            # We use a short wait to trigger C_01 if the semaphore is stuck
            await asyncio.wait_for(self._global_semaphore.acquire(), timeout=300)
            try:
                kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "keep_alive": 0,
                }
                if options is not None:
                    kwargs["options"] = options
                if tools is not None:
                    kwargs["tools"] = tools
                if think is not None:
                    kwargs["think"] = think

                res = await self._client.chat(**kwargs)
                return res
            finally:
                self._global_semaphore.release()
        except TimeoutError as exc:
            logger.warning("ollama_semaphore_timeout")
            raise exc

    async def generate(self, model: str, prompt: str, format: str = "") -> Any:
        """Sends a generate request with strict keep_alive=0."""
        try:
            await asyncio.wait_for(self._global_semaphore.acquire(), timeout=300)
            try:
                kwargs: dict[str, Any] = {
                    "model": model,
                    "prompt": prompt,
                    "keep_alive": 0,
                }
                if format:
                    kwargs["format"] = format
                res = await self._client.generate(**kwargs)
                return res
            finally:
                self._global_semaphore.release()
        except TimeoutError as exc:
            logger.warning("ollama_semaphore_timeout")
            raise exc

    async def embed(self, model: str, input_texts: list[str]) -> Any:
        """Sends an embedding request with strict keep_alive=0."""
        try:
            await asyncio.wait_for(self._global_semaphore.acquire(), timeout=300)
            try:
                res = await self._client.embed(
                    model=model,
                    input=input_texts,
                    keep_alive=0,
                )
                return res
            finally:
                self._global_semaphore.release()
        except TimeoutError as exc:
            logger.warning("ollama_semaphore_timeout")
            raise exc

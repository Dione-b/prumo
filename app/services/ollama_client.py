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
            await asyncio.wait_for(
                self._global_semaphore.acquire(),
                timeout=settings.ollama_request_timeout,
            )
            try:
                kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                }

                final_options: dict[str, Any] = {
                    "keep_alive": settings.ollama_keep_alive,
                }
                if options is not None:
                    final_options.update(options)
                kwargs["options"] = final_options

                if tools is not None:
                    kwargs["tools"] = tools
                if think:
                    kwargs["think"] = True

                res = await self._client.chat(**kwargs)
                return res
            finally:
                self._global_semaphore.release()
        except TimeoutError as exc:
            logger.warning("ollama_semaphore_timeout")
            raise exc

    async def generate(self, model: str, prompt: str, format: str = "") -> Any:
        """Sends a generate request with strict VRAM offload."""
        try:
            await asyncio.wait_for(
                self._global_semaphore.acquire(),
                timeout=settings.ollama_request_timeout,
            )
            try:
                kwargs: dict[str, Any] = {
                    "model": model,
                    "prompt": prompt,
                    "options": {"keep_alive": settings.ollama_keep_alive},
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
        """Sends an embedding request with strict VRAM offload."""
        try:
            await asyncio.wait_for(
                self._global_semaphore.acquire(),
                timeout=settings.ollama_request_timeout,
            )
            try:
                res = await self._client.embed(
                    model=model,
                    input=input_texts,
                    options={"keep_alive": settings.ollama_keep_alive},
                )
                return res
            finally:
                self._global_semaphore.release()
        except TimeoutError as exc:
            logger.warning("ollama_semaphore_timeout")
            raise exc

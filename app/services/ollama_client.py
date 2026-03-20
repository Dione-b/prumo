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


"""OllamaClient — centralized local model access with simple semaphore."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from ollama import AsyncClient

from app.config import settings

logger = structlog.get_logger()


class OllamaClient:
    """Centraliza acesso aos modelos Ollama com controle de concorrência simples."""

    def __init__(self) -> None:
        self._semaphore = asyncio.Semaphore(settings.ollama_max_concurrent)
        self._client = AsyncClient(host=settings.ollama_base_url)

    async def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        think: bool = True,
        options: dict[str, Any] | None = None,
    ) -> Any:
        """Envia requisição de chat com controle de concorrência."""
        async with self._semaphore:
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

            return await self._client.chat(**kwargs)

    async def embed(self, model: str, input_texts: list[str]) -> Any:
        """Gera embeddings com controle de concorrência."""
        async with self._semaphore:
            return await self._client.embed(
                model=model,
                input=input_texts,
                options={"keep_alive": settings.ollama_keep_alive},
            )

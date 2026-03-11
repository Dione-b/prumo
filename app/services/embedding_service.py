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


"""Embedding service for graph nodes using Qwen3 via Ollama.

Fetches nodes with missing embeddings from the database, generates
embeddings in batches natively async via ollama.AsyncClient, and writes them
back. This service NEVER calls session.commit() — the transaction
boundary belongs to the task owner (C_03).
"""

from __future__ import annotations

import structlog

from app.config import settings
from app.services.ollama_client import OllamaClient

logger = structlog.get_logger()


class EmbeddingService:
    """Sequential embedding service to protect VRAM."""

    def __init__(self) -> None:
        self.ollama_client = OllamaClient()

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a batch of texts sequentially.
        1. Iterate texts sequentially.
        2. Call self.ollama_client.embed for each.
        """
        # [IMPLEMENTATION START]
        embeddings: list[list[float]] = []
        for text in texts:
            # sequentially embed to ensure no VRAM overlap
            res = await self.ollama_client.embed(
                model=settings.ollama_embedding_model,
                input_texts=[text],
            )
            embeddings.extend(res.embeddings)  # type: ignore[attr-defined]
        return embeddings

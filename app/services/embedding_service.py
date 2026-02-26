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

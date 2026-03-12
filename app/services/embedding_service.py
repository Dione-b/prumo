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


"""Embedding service using Gemini text-embedding-004.

Delegates all embedding calls to GeminiClient. This service NEVER calls
session.commit() — the transaction boundary belongs to the task owner.
"""

from __future__ import annotations

import structlog

from app.services.gemini_client import GeminiClient

logger = structlog.get_logger()


class EmbeddingService:
    """Embedding service backed by Gemini text-embedding-004."""

    def __init__(self, client: GeminiClient | None = None) -> None:
        self._client = client or GeminiClient()

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts via Gemini API.

        Embeds sequentially to respect API rate limits.
        """
        return await self._client.embed_batch(texts)

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


"""Strict Step-by-Step Orchestrator: Extraction -> Embedding."""

from __future__ import annotations

import structlog

from app.domain.ports import EmbeddingPort, LLMEnginePort
from app.infrastructure.llm_external import EmbeddingServiceAdapter, ExternalAIEngineAdapter
from app.schemas.graph import EntityExtractionResult

logger = structlog.get_logger()


class DocumentProcessor:
    """Strict Step-by-Step Orchestrator: Extraction -> Embedding."""

    def __init__(
        self,
        llm_engine: LLMEnginePort | None = None,
        embedding_service: EmbeddingPort | None = None,
    ) -> None:
        self.llm_engine = llm_engine or ExternalAIEngineAdapter()
        self.embedding_service = embedding_service or EmbeddingServiceAdapter()

    async def process_document(
        self, raw_content: str, system_prompt: str
    ) -> tuple[EntityExtractionResult, list[list[float]]]:
        """
        Linear pipeline to avoid hardware contention:
        Step 1: Extract (Gemini Flash via LLMGateway) -> Model output.
        Step 2: Embed (Gemini text-embedding-004).
        """
        # Step 1: Extract (Gemini Flash)
        logger.info("document_process_extraction_start")
        extracted = await self.llm_engine.extract_entities(
            raw_content,
            system_prompt=system_prompt,
        )
        extraction = EntityExtractionResult(
            entities=[
                {
                    "name": entity.name,
                    "entity_type": entity.entity_type,
                    "description": entity.description,
                    "is_valid": entity.is_valid,
                }
                for entity in extracted.entities
            ],
            relations=[
                {
                    "source": relation.source,
                    "target": relation.target,
                    "relation_type": relation.relation_type,
                    "description": relation.description,
                    "confidence": relation.confidence,
                    "is_valid": relation.is_valid,
                }
                for relation in extracted.relations
            ],
        )

        # Step 2: Embed (Gemini text-embedding-004)
        logger.info("document_process_embedding_start")
        texts_to_embed = [
            f"{entity.name}: {entity.description}" for entity in extraction.entities
        ]
        embeddings = await self.embedding_service.embed_batch(texts_to_embed)

        return extraction, embeddings

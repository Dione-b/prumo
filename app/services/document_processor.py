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
        Step 1: Extract (Ollama/MiniMax via LLMGateway) -> Model Unloads.
        Step 2: Embed (Qwen2.5) -> Model Unloads.
        """
        # Step 1: Extract (Ollama Graph Model)
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

        # Step 2: Embed (Qwen2.5)
        logger.info("document_process_embedding_start")
        texts_to_embed = [
            f"{entity.name}: {entity.description}" for entity in extraction.entities
        ]
        embeddings = await self.embedding_service.embed_batch(texts_to_embed)

        return extraction, embeddings

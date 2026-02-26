"""Strict Step-by-Step Orchestrator: Extraction -> Embedding."""

from __future__ import annotations

import structlog

from app.schemas.graph import EntityExtractionResult
from app.services.embedding_service import EmbeddingService
from app.services.llm_gateway import LLMGateway

logger = structlog.get_logger()


class DocumentProcessor:
    """Strict Step-by-Step Orchestrator: Extraction -> Embedding."""

    def __init__(self) -> None:
        self.gateway = LLMGateway()
        self.embedding_service = EmbeddingService()

    async def process_document(
        self, raw_content: str
    ) -> tuple[EntityExtractionResult, list[list[float]]]:
        """
        Linear pipeline to avoid hardware contention:
        Step 1: Extract (Llama 3.2) -> Model Unloads.
        Step 2: Embed (Qwen2.5) -> Model Unloads.

        Note: Persistence of extraction result and embeddings must be managed
        by the caller via background tasks (C_03). This function only returns
        the DTOs and handles no DB commits directly, except we return extraction
        and caller persists, then we generate embeddings?
        Actually, if we need to return embeddings for the caller to save, we wait
        to see how the caller uses it. Since "Step 2" is here, we should probably
        do both here, or just return the extraction so the caller saves nodes,
        and then calls embed separately. Let's define it all here.
        """
        # Step 1: Extract (Llama 3.2)
        logger.info("document_process_extraction_start")
        extraction = await self.gateway.extract_business_rules(
            raw_content, EntityExtractionResult
        )

        # Step 2: Embed (Qwen2.5)
        logger.info("document_process_embedding_start")
        texts_to_embed = [
            f"{entity.name}: {entity.description}" for entity in extraction.entities
        ]
        embeddings = await self.embedding_service.embed_batch(texts_to_embed)

        return extraction, embeddings

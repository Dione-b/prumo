from __future__ import annotations

from app.domain.entities import (
    BusinessRuleExtraction,
    GraphRelation,
    KnowledgeEntity,
    KnowledgeEntityExtraction,
)
from app.schemas.business_rule import BusinessRuleSchema
from app.schemas.graph import EntityExtractionResult
from app.services.embedding_service import EmbeddingService
from app.services.llm_gateway import LLMGateway


class ExternalAIEngineAdapter:
    """Infrastructure adapter that hides concrete LLM providers from the core."""

    def __init__(self, gateway: LLMGateway | None = None) -> None:
        self._gateway = gateway or LLMGateway()

    async def extract_business_rules(self, text: str) -> BusinessRuleExtraction:
        result = await self._gateway.extract_business_rules(text, BusinessRuleSchema)
        return BusinessRuleExtraction(
            client_name=result.client_name,
            core_objective=result.core_objective,
            technical_constraints=tuple(result.technical_constraints),
            acceptance_criteria=tuple(result.acceptance_criteria),
            additional_notes=result.additional_notes,
            confidence_level=result.confidence_level,
            warnings=tuple(result.warnings),
        )

    async def extract_entities(
        self,
        text: str,
        system_prompt: str | None = None,
    ) -> KnowledgeEntityExtraction:
        prompt = system_prompt or (
            "You are an expert technical extractor. "
            "Return valid structured entities and relations."
        )
        result = await self._gateway.extract_graph_entities(
            text,
            EntityExtractionResult,
            prompt,
        )
        return KnowledgeEntityExtraction(
            entities=tuple(
                KnowledgeEntity(
                    name=entity.name,
                    entity_type=entity.entity_type,
                    description=entity.description,
                    is_valid=entity.is_valid,
                )
                for entity in result.entities
            ),
            relations=tuple(
                GraphRelation(
                    source=relation.source,
                    target=relation.target,
                    relation_type=relation.relation_type,
                    description=relation.description,
                    confidence=relation.confidence,
                    is_valid=relation.is_valid,
                )
                for relation in result.relations
            ),
        )


class EmbeddingServiceAdapter:
    def __init__(self, service: EmbeddingService | None = None) -> None:
        self._service = service or EmbeddingService()

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return await self._service.embed_batch(texts)

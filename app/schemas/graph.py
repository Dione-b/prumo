from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExtractedEntity(BaseModel):
    """Single entity extracted by the LLM from a text chunk."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(..., min_length=1, max_length=255)
    entity_type: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Category of the entity (e.g. 'CONCEPT', 'PROTOCOL', 'LIBRARY').",
    )
    description: str = Field(
        ...,
        min_length=1,
        description="Concise explanation of what this entity represents.",
    )


class ExtractedRelation(BaseModel):
    """Directed relation between two extracted entities."""

    model_config = ConfigDict(frozen=True)

    source: str = Field(..., min_length=1, description="Name of the source entity.")
    target: str = Field(..., min_length=1, description="Name of the target entity.")
    relation_type: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Verb or phrase describing the relationship.",
    )
    description: str = Field(
        ..., min_length=1, description="Contextual detail about this relation."
    )
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = "MEDIUM"


class EntityExtractionResult(BaseModel):
    """Aggregate output from entity/relation extraction on a single chunk.

    The model_validator (C_01) ensures no dangling relation references exist —
    every relation's source and target must map to an entity in the same result.
    """

    model_config = ConfigDict(frozen=True)

    entities: list[ExtractedEntity] = Field(default_factory=list)
    relations: list[ExtractedRelation] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_no_dangling_relations(self) -> EntityExtractionResult:
        """C_01: Validate all relation endpoints reference known entities."""
        entity_names = {e.name for e in self.entities}
        dangling: list[str] = []

        for rel in self.relations:
            if rel.source not in entity_names:
                dangling.append(
                    f"source '{rel.source}' in "
                    f"relation '{rel.relation_type}'"
                )
            if rel.target not in entity_names:
                dangling.append(
                    f"target '{rel.target}' in "
                    f"relation '{rel.relation_type}'"
                )

        if dangling:
            # Remove dangling relations instead of raising — LLM output is noisy.
            clean_relations = [
                r
                for r in self.relations
                if r.source in entity_names and r.target in entity_names
            ]
            object.__setattr__(self, "relations", clean_relations)

        return self


class NodeContext(BaseModel):
    """A graph node returned as part of a query result with its relevance score."""

    model_config = ConfigDict(frozen=True)

    name: str
    entity_type: str
    description: str
    score: float = Field(..., ge=0.0, le=1.0, description="Cosine similarity score.")
    community_id: int | None = None


class EdgeContext(BaseModel):
    """An edge connecting two nodes, included in expanded query context."""

    model_config = ConfigDict(frozen=True)

    source_name: str
    target_name: str
    relation_type: str
    description: str
    weight: float = 1.0
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = "MEDIUM"


class CommunityInfo(BaseModel):
    """Summary of a detected community for global-level queries."""

    model_config = ConfigDict(frozen=True)

    community_id: int
    summary: str
    member_count: int = Field(..., ge=1)

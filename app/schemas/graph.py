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


from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


class ExtractedEntity(BaseModel):
    """Single entity extracted by the LLM from a text chunk."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=255)
    entity_type: str = Field(
        ...,
        validation_alias=AliasChoices(
            "entity_type", "Entity_Type", "type", "entityType"
        ),
        min_length=1,
        max_length=50,
        description="Category of the entity (e.g. 'CONCEPT', 'PROTOCOL', 'LIBRARY').",
    )
    description: str = Field(
        ...,
        min_length=1,
        description="Concise explanation of what this entity represents.",
    )
    is_valid: bool = True


class ExtractedRelation(BaseModel):
    """Directed relation between two extracted entities."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    source: str = Field(..., min_length=1, description="Name of the source entity.")
    target: str = Field(..., min_length=1, description="Name of the target entity.")
    relation_type: str = Field(
        ...,
        validation_alias=AliasChoices(
            "relation_type", "Relation_Type", "type", "relationType"
        ),
        min_length=1,
        max_length=100,
        description="Verb or phrase describing the relationship.",
    )
    description: str = Field(
        ..., min_length=1, description="Contextual detail about this relation."
    )
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = "MEDIUM"
    is_valid: bool = True


class EntityExtractionResult(BaseModel):
    """Aggregate output from entity/relation extraction on a single chunk.

    The model_validator (C_01) ensures no dangling relation references exist —
    every relation's source and target must map to an entity in the same result.
    """

    model_config = ConfigDict(frozen=True)

    entities: list[ExtractedEntity] = Field(default_factory=list)
    relations: list[ExtractedRelation] = Field(default_factory=list)

    @model_validator(mode="after")
    def flag_dangling_relations(self) -> EntityExtractionResult:
        """C_01: Flag any relation endpoints that reference unknown entities.
        Instead of removing them, flip is_valid to False.
        """
        entity_names = {e.name for e in self.entities}
        dangling: list[str] = []

        for rel in self.relations:
            if rel.source not in entity_names:
                dangling.append(
                    f"source '{rel.source}' in relation '{rel.relation_type}'"
                )
            if rel.target not in entity_names:
                dangling.append(
                    f"target '{rel.target}' in relation '{rel.relation_type}'"
                )

        if dangling:
            updated_relations = []
            for r in self.relations:
                if r.source not in entity_names or r.target not in entity_names:
                    # Mutable assignment em modelo Pydantic frozen
                    updated_rel = r.model_copy()
                    object.__setattr__(updated_rel, "is_valid", False)
                    updated_relations.append(updated_rel)
                else:
                    updated_relations.append(r)

            object.__setattr__(self, "relations", updated_relations)

        return self


class NodeContext(BaseModel):
    """A graph node returned as part of a query result with its relevance score."""

    model_config = ConfigDict(frozen=True)

    name: str
    entity_type: str
    description: str
    score: float = Field(..., ge=0.0, le=1.0, description="Cosine similarity score.")
    community_id: int | None = None
    is_valid: bool = True


class EdgeContext(BaseModel):
    """An edge connecting two nodes, included in expanded query context."""

    model_config = ConfigDict(frozen=True)

    source_name: str
    target_name: str
    relation_type: str
    description: str
    weight: float = 1.0
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = "MEDIUM"
    is_valid: bool = True


class CommunityInfo(BaseModel):
    """Summary of a detected community for global-level queries."""

    model_config = ConfigDict(frozen=True)

    community_id: int
    summary: str
    member_count: int = Field(..., ge=1)

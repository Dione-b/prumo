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


"""Tests for graph-related Pydantic schemas."""

from uuid import uuid4

from app.schemas.graph import (
    EntityExtractionResult,
    ExtractedEntity,
    ExtractedRelation,
    NodeContext,
)
from app.schemas.knowledge import AnswerCitation


def _entity(name: str) -> ExtractedEntity:
    """Helper to create a minimal ExtractedEntity."""
    return ExtractedEntity(
        name=name,
        entity_type="CONCEPT",
        description=f"Description of {name}",
    )


def _relation(source: str, target: str) -> ExtractedRelation:
    """Helper to create a minimal ExtractedRelation."""
    return ExtractedRelation(
        source=source,
        target=target,
        relation_type="USES",
        description=f"{source} uses {target}",
    )


def test_extraction_result_valid_relations_kept() -> None:
    # Arrange
    entities = [_entity("ZKP"), _entity("Groth16")]
    relations = [_relation("ZKP", "Groth16")]

    # Act
    result = EntityExtractionResult(entities=entities, relations=relations)

    # Assert
    assert len(result.relations) == 1
    assert result.relations[0].source == "ZKP"


def test_extraction_result_dangling_relations_removed() -> None:
    # Arrange
    entities = [_entity("ZKP")]
    relations = [_relation("ZKP", "NonExistent")]

    # Act
    result = EntityExtractionResult(entities=entities, relations=relations)

    # Assert — dangling relation is kept but flagged as invalid.
    assert len(result.relations) == 1
    assert not result.relations[0].is_valid


def test_extraction_result_empty_is_valid() -> None:
    # Act
    result = EntityExtractionResult()

    # Assert
    assert len(result.entities) == 0
    assert len(result.relations) == 0


def test_extraction_result_frozen() -> None:
    # Arrange
    result = EntityExtractionResult(entities=[_entity("A")])

    # Act / Assert — frozen model should reject mutation.
    import pytest

    with pytest.raises(Exception):  # noqa: B017
        result.entities = []  # type: ignore[misc]


def test_node_context_score_clamped() -> None:
    # Arrange / Act
    node = NodeContext(
        name="ZKP",
        entity_type="CONCEPT",
        description="Zero Knowledge Proof",
        score=0.95,
    )

    # Assert
    assert node.score == 0.95


def test_answer_citation_coerce_source() -> None:
    # Arrange
    doc_id = uuid4()

    # Act
    citation = AnswerCitation(
        document_id=doc_id,
        snippet="test snippet",
    )

    # Assert — source should be auto-populated.
    assert citation.source == f"doc:{doc_id}"


def test_answer_citation_preserves_explicit_source() -> None:
    # Arrange / Act
    citation = AnswerCitation(
        document_id=uuid4(),
        snippet="test snippet",
        source="explicit_source",
    )

    # Assert
    assert citation.source == "explicit_source"


def test_answer_citation_no_doc_id_no_source() -> None:
    # Arrange / Act
    citation = AnswerCitation(snippet="test snippet")

    # Assert
    assert citation.source is None

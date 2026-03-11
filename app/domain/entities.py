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

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID

ConfidenceLevel = Literal["HIGH", "MEDIUM", "LOW"]
KnowledgeDocumentStatus = Literal[
    "PENDING",
    "PROCESSING",
    "READY",
    "READY_PARTIAL",
    "ERROR",
]
QueryMode = Literal["local", "global", "hybrid"]


@dataclass(frozen=True, slots=True)
class ProjectDraft:
    name: str
    stack: str
    description: str | None = None


@dataclass(frozen=True, slots=True)
class ProjectRecord:
    id: UUID
    name: str
    description: str | None
    llm_model: str
    namespace: str


@dataclass(frozen=True, slots=True)
class BusinessRuleExtraction:
    client_name: str
    core_objective: str
    technical_constraints: tuple[str, ...] = ()
    acceptance_criteria: tuple[str, ...] = ()
    additional_notes: str | None = None
    confidence_level: ConfidenceLevel = "LOW"
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BusinessRuleDraft:
    project_id: UUID
    raw_text: str
    extraction: BusinessRuleExtraction
    source: str | None = None


@dataclass(frozen=True, slots=True)
class BusinessRuleRecord:
    id: UUID
    project_id: UUID
    raw_text: str
    client_name: str
    core_objective: str
    technical_constraints: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    additional_notes: str | None
    confidence_level: ConfidenceLevel
    source: str | None


@dataclass(frozen=True, slots=True)
class KnowledgeEntity:
    name: str
    entity_type: str
    description: str
    is_valid: bool = True


@dataclass(frozen=True, slots=True)
class GraphRelation:
    source: str
    target: str
    relation_type: str
    description: str
    confidence: ConfidenceLevel = "MEDIUM"
    is_valid: bool = True


@dataclass(frozen=True, slots=True)
class KnowledgeEntityExtraction:
    entities: tuple[KnowledgeEntity, ...] = ()
    relations: tuple[GraphRelation, ...] = ()


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentDraft:
    project_id: UUID
    title: str
    source_type: str
    content: str | None = None
    metadata: dict[str, object] | None = None
    status: KnowledgeDocumentStatus = "PROCESSING"


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentRecord:
    id: UUID
    project_id: UUID
    title: str
    source_type: str
    status: KnowledgeDocumentStatus
    gemini_file_uri: str | None
    gemini_cache_name: str | None
    cache_expires_at: datetime | None
    raw_content: str | None
    metadata_json: dict[str, object] | None = field(default=None)


@dataclass(frozen=True, slots=True)
class AnswerCitation:
    document_id: UUID | None
    snippet: str
    source: str | None = None


@dataclass(frozen=True, slots=True)
class KnowledgeAnswerResult:
    answer: str
    confidence_level: ConfidenceLevel
    citations: tuple[AnswerCitation, ...] = ()
    warnings: tuple[str, ...] = ()

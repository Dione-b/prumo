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


"""Graph entity/relation extractor using Gemini Flash structured output.

Responsibility: extract entities and relations from text chunks, then
upsert them into the graph tables. This service NEVER calls session.commit()
— the transaction boundary belongs exclusively to the task owner
(process_document_task).

The `safe_extract_and_upsert` function wraps the full extraction pipeline
in a resilient try/except that returns a structured report, allowing the
caller to derive READY_PARTIAL status without aborting the entire batch.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from dataclasses import dataclass
from uuid import UUID

import structlog
from google import genai
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.graph import GraphEdge, GraphNode
from app.schemas.graph import EntityExtractionResult, ExtractedEntity, ExtractedRelation
from app.services.document_processor import DocumentProcessor

logger = structlog.get_logger()

client = genai.Client(api_key=settings.gemini_api_key.get_secret_value())


@dataclass(frozen=True)
class GraphExtractionReport:
    """Immutable status report for a single document's graph extraction attempt."""

    document_id: UUID
    success: bool
    entities_count: int = 0
    relations_count: int = 0
    error: str | None = None
    skipped: bool = False
    skip_reason: str | None = None
    confidence_downgrade: str | None = None


# Rate-limit pause between Flash calls — configurable via GEMINI_FLASH_DELAY_MS.
_FLASH_RATE_LIMIT_SECONDS = settings.gemini_flash_delay_ms / 1000.0

# Maximum characters per chunk sent for extraction.
# Takes advantage of large context window models (e.g. MiniMax M2 200k tokens).
_MAX_CHUNK_SIZE = 100_000

_EXTRACTION_SYSTEM_INSTRUCTION = (
    "You are a precise, agentic knowledge-graph extraction engine, specialized "
    "in Rust and Soroban smart contract architectures. "
    "Given a chunk of technical text, extract ALL named entities "
    "(concepts, protocols, functions, data structures, people, "
    "organizations) and ALL directed relations between them. "
    "You have the capability of 'multi-file edits' perspective: use this broad "
    "context to resolve and eliminate any contradictions before outputting. "
    "Each entity must have a concise but informative description. "
    "Each relation must specify source, target, relation_type (a verb phrase), "
    "description, and confidence (HIGH/MEDIUM/LOW). "
    "Output ONLY valid JSON matching the provided schema. "
    "CRITICAL: You must use EXACTLY the keys provided in the JSON schema. "
    "Use 'entity_type', NOT 'Entity_Type'. "
    "Do NOT invent entities not present in the text. "
    "Prioritize accuracy and conceptual consistency in your extractions."
)


def _chunk_text(raw_content: str, max_size: int = _MAX_CHUNK_SIZE) -> list[str]:
    """Split raw document content into manageable chunks for extraction."""
    if len(raw_content) <= max_size:
        return [raw_content]

    chunks: list[str] = []
    lines = raw_content.split("\n")
    current_chunk: list[str] = []
    current_size = 0

    for line in lines:
        line_size = len(line) + 1  # +1 for the newline
        if current_size + line_size > max_size and current_chunk:
            chunks.append("\n".join(current_chunk))
            current_chunk = []
            current_size = 0
        current_chunk.append(line)
        current_size += line_size

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    return chunks


def _extract_from_chunk_sync(chunk: str) -> EntityExtractionResult:
    """Synchronous Flash call — intended to run in a thread via asyncio.to_thread.

    Honra C_03: instancia GenerativeModel por chamada, sem singleton,
    porque cada thread precisa da sua própria instância.
    """
    response = client.models.generate_content(
        model=settings.gemini_flash_model,
        contents=chunk,
        config=genai.types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=EntityExtractionResult,
            temperature=0.0,
            system_instruction=_EXTRACTION_SYSTEM_INSTRUCTION,
        ),
    )

    return EntityExtractionResult.model_validate_json(str(response.text))


async def extract_entities_from_chunks(
    raw_content: str,
) -> EntityExtractionResult:
    """Extract entities and relations from a document's raw text.

    Splits the text into chunks, sends each to Flash for extraction,
    and merges the results. Respects rate limits with asyncio.sleep().
    """
    chunks = _chunk_text(raw_content)
    all_entities: list[ExtractedEntity] = []
    all_relations: list[ExtractedRelation] = []

    for i, chunk in enumerate(chunks):
        if i > 0:
            await asyncio.sleep(_FLASH_RATE_LIMIT_SECONDS)

        try:
            result = await asyncio.to_thread(_extract_from_chunk_sync, chunk)
            all_entities.extend(result.entities)
            all_relations.extend(result.relations)
        except Exception:  # noqa: BLE001
            logger.warning(
                "chunk_extraction_failed",
                chunk_index=i,
                total_chunks=len(chunks),
            )
            # Continue with remaining chunks — partial extraction is acceptable.

    return EntityExtractionResult(
        entities=all_entities,
        relations=all_relations,
    )


async def upsert_graph_data(
    session: AsyncSession,
    project_id: UUID,
    document_id: UUID,
    extraction: EntityExtractionResult,
    embeddings: list[list[float]] | None = None,
) -> int:
    """Upsert extracted entities and relations into graph tables.

    Uses ON CONFLICT DO UPDATE for nodes (merging source_document_ids)
    and plain INSERT for edges. Does NOT call session.commit() — the
    transaction boundary belongs to the task owner (C_03).

    Returns the total number of nodes upserted.
    """
    if not extraction.entities:
        return 0

    doc_id_str = str(document_id)
    node_name_to_id: dict[str, uuid.UUID] = {}

    for i, entity in enumerate(extraction.entities):
        hash_input = f"{entity.name}:{entity.entity_type}:{project_id}".encode()
        node_id = uuid.UUID(hashlib.sha256(hash_input).hexdigest()[:32])

        upsert_stmt = text("""
            INSERT INTO graph_nodes (
                id, project_id, name, entity_type,
                description, source_document_ids, embedding
            )
            VALUES (
                :id, :project_id, :name, :entity_type,
                :description, :source_doc_ids::jsonb, :embedding
            )
            ON CONFLICT (project_id, name) DO UPDATE SET
                description = EXCLUDED.description,
                entity_type = EXCLUDED.entity_type,
                embedding = COALESCE(EXCLUDED.embedding, graph_nodes.embedding),
                source_document_ids = (
                    SELECT jsonb_agg(DISTINCT elem)
                    FROM jsonb_array_elements(
                        graph_nodes.source_document_ids || EXCLUDED.source_document_ids
                    ) AS elem
                ),
                updated_at = NOW()
            RETURNING id
        """)

        result = await session.execute(
            upsert_stmt,
            {
                "id": str(node_id),
                "project_id": str(project_id),
                "name": entity.name,
                "entity_type": entity.entity_type,
                "description": entity.description,
                "source_doc_ids": f'["{doc_id_str}"]',
                "embedding": (
                    json.dumps(embeddings[i])
                    if embeddings and i < len(embeddings)
                    else None
                ),
            },
        )

        # ON CONFLICT RETURNING may not return a row with asyncpg in no-op cases.
        # Always do a SELECT to confirm the node ID.
        returned = result.first()
        if returned:
            node_name_to_id[entity.name] = returned[0]
        else:
            select_result = await session.execute(
                select(GraphNode.id).where(
                    GraphNode.project_id == project_id,
                    GraphNode.name == entity.name,
                )
            )
            existing = select_result.scalar_one_or_none()
            if existing:
                node_name_to_id[entity.name] = existing

    # --- Insert edges ---
    for relation in extraction.relations:
        source_id = node_name_to_id.get(relation.source)
        target_id = node_name_to_id.get(relation.target)

        if source_id is None or target_id is None:
            logger.debug(
                "skipping_edge_missing_node",
                source=relation.source,
                target=relation.target,
            )
            continue

        edge = GraphEdge(
            project_id=project_id,
            source_node_id=source_id,
            target_node_id=target_id,
            relation_type=relation.relation_type,
            description=relation.description,
            confidence=relation.confidence,
            source_document_ids=[doc_id_str],
            is_valid=relation.is_valid,
        )
        session.add(edge)

    await session.flush()

    logger.info(
        "graph_data_upserted",
        project_id=str(project_id),
        document_id=doc_id_str,
        nodes_upserted=len(node_name_to_id),
        edges_created=len(extraction.relations),
    )

    return len(node_name_to_id)


async def remove_document_graph_data(session: AsyncSession, document_id: UUID) -> None:
    """Remover os nós e arestas antigos de um documento (Swap de Reprocessamento).

    Removemos o document_id dos source_document_ids (JSONB Array) na tabela graph_edges.
    Se a aresta não pertencer a mais nenhum documento, ela é deletada.
    Em seguida, repetimos a operação para os graph_nodes.
    """
    doc_id_str = str(document_id)
    doc_id_json = f'["{doc_id_str}"]'

    # 1. Update/Delete EDGES
    await session.execute(
        text(
            """
            WITH updated_edges AS (
                UPDATE graph_edges
                SET source_document_ids = source_document_ids - :doc_id_str
                WHERE source_document_ids @> :doc_id_json
                RETURNING id, source_document_ids
            )
            DELETE FROM graph_edges WHERE id IN (
                SELECT id FROM updated_edges WHERE jsonb_array_length(source_document_ids) = 0
            )
            """
        ),
        {"doc_id_str": doc_id_str, "doc_id_json": doc_id_json},
    )

    # 2. Update/Delete NODES
    await session.execute(
        text(
            """
            WITH updated_nodes AS (
                UPDATE graph_nodes
                SET source_document_ids = source_document_ids - :doc_id_str
                WHERE source_document_ids @> :doc_id_json
                RETURNING id, source_document_ids
            )
            DELETE FROM graph_nodes WHERE id IN (
                SELECT id FROM updated_nodes WHERE jsonb_array_length(source_document_ids) = 0
            )
            """
        ),
        {"doc_id_str": doc_id_str, "doc_id_json": doc_id_json},
    )


async def extract_graph_data(
    raw_content: str | None,
    is_binary: bool,
) -> tuple[EntityExtractionResult | None, list[list[float]] | None, str | None]:
    """Isola a Extração: Retorna (Extração, Embeddings, Reason) sem tocar no BD."""
    if is_binary:
        return None, None, "binary files are processed via File API only"
    if not raw_content:
        return None, None, "no raw_content available for extraction"

    processor = DocumentProcessor()
    extraction, embeddings = await processor.process_document(
        raw_content, _EXTRACTION_SYSTEM_INSTRUCTION
    )

    if not extraction.entities:
        return None, None, "no entities found in content"

    return extraction, embeddings, None

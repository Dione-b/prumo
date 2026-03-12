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


"""Code generation service using Gemini Pro + Graph RAG context."""

from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.gemini_client import GeminiClient

logger = structlog.get_logger()

_CODEGEN_SYSTEM_INSTRUCTION = (
    "You are an expert code generation assistant. "
    "Given a task description and existing code context from the project, "
    "generate clean, well-documented code that follows the project's patterns "
    "and conventions. "
    "RULES: "
    "1. Follow the coding style visible in the context examples. "
    "2. Use proper type hints and docstrings. "
    "3. Do NOT generate code that contradicts existing patterns. "
    "4. If the task is ambiguous, state assumptions clearly in comments. "
    "5. Output ONLY the code, no markdown fences or explanations."
)


class CodegenService:
    """Code generation backed by Graph RAG context retrieval."""

    def __init__(self, client: GeminiClient | None = None) -> None:
        self._client = client or GeminiClient()

    async def generate(
        self,
        session: AsyncSession,
        task: str,
        project_id: UUID,
        language: str = "python",
    ) -> str:
        """Generate code for a task using relevant context from the graph.

        1. Embed the task description.
        2. Find similar entities (code snippets, functions, classes).
        3. Build context from matching entities.
        4. Call Gemini Pro with task + context for generation.
        """
        # Step 1: Embed the task
        task_embedding = await self._client.embed(task)

        # Step 2: Find similar code entities
        similar_nodes = await self._find_similar_entities(
            session, project_id, task_embedding,
        )

        # Step 3: Build context
        context = self._build_context(similar_nodes, language)

        # Step 4: Generate
        prompt = (
            f"LANGUAGE: {language}\n\n"
            f"EXISTING CODE CONTEXT:\n{context}\n\n"
            f"TASK:\n{task}\n\n"
            "Generate the code:"
        )

        return await self._client.generate_text(
            prompt=prompt,
            system_instruction=_CODEGEN_SYSTEM_INSTRUCTION,
            model=settings.gemini_synthesis_model,
            temperature=0.1,
        )

    async def _find_similar_entities(
        self,
        session: AsyncSession,
        project_id: UUID,
        query_embedding: list[float],
        top_k: int = 5,
    ) -> list[dict[str, str]]:
        """Find relevant code entities via pgvector cosine similarity."""
        stmt = text("""
            SELECT name, entity_type, description,
                   1 - (embedding <=> :query_embedding::vector) AS score
            FROM graph_nodes
            WHERE project_id = :project_id
                AND embedding IS NOT NULL
                AND is_valid = true
            ORDER BY embedding <=> :query_embedding::vector
            LIMIT :top_k
        """)

        result = await session.execute(
            stmt,
            {
                "project_id": str(project_id),
                "query_embedding": str(query_embedding),
                "top_k": top_k,
            },
        )

        return [
            {
                "name": row[0],
                "type": row[1],
                "description": row[2],
                "score": f"{float(row[3]):.2f}",
            }
            for row in result.all()
        ]

    def _build_context(
        self,
        nodes: list[dict[str, str]],
        language: str,
    ) -> str:
        """Format similar entities as context for code generation."""
        if not nodes:
            return f"No existing {language} code context found."

        lines = [f"=== RELEVANT {language.upper()} ENTITIES ==="]
        for node in nodes:
            lines.append(
                f"- {node['name']} [{node['type']}] "
                f"(relevance: {node['score']}): {node['description']}"
            )
        return "\n".join(lines)

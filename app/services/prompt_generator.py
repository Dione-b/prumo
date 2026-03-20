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


"""PromptGeneratorService — gera prompts YAML estruturados para agentes LLM.

Combina regras de negócio do projeto, contexto relevante via busca vetorial
(pgvector), e um template de prompt genérico em YAML.

Invariantes:
  C_03: NUNCA chama session.commit() — caller owns the transaction.
"""

from __future__ import annotations

from uuid import UUID

import structlog
import yaml
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.strategies.generic_strategy import GenericStrategy
from app.domain.strategies.prompt_strategy import StrategyPayload
from app.interfaces.storage import IOutputStorage
from app.models.business_rule import BusinessRule
from app.schemas.prompt_generator import GeneratedPrompt, PromptStrategyConfig
from app.services.embedding_service import EmbeddingService

logger = structlog.get_logger()

_MAX_BUSINESS_RULES = 5
TOP_K_CONTEXT = 5


class PromptGeneratorService:
    """Gera prompts YAML combinando regras de negócio e contexto RAG."""

    def __init__(self, storage: IOutputStorage) -> None:
        self._storage = storage
        self._strategy = GenericStrategy()

    async def generate_prompt(
        self,
        session: AsyncSession,
        project_id: UUID,
        task_intent: str,
        target_files: list[str],
        strategy_overrides: PromptStrategyConfig | None = None,
    ) -> GeneratedPrompt:
        """Monta prompt YAML para agentes downstream.

        C_03: NUNCA commita — caller owns the transaction.
        """
        cfg = strategy_overrides or PromptStrategyConfig()
        warnings: list[str] = []
        payload = self._strategy.get_payload()

        # 1. Buscar constraints do projeto
        prohibited, required = await self._build_constraints(
            session, project_id, cfg, payload
        )

        # 2. Buscar contexto relevante via RAG (pgvector)
        rag_context = await self._fetch_rag_context(
            session, project_id, task_intent, warnings
        )

        # 3. Montar YAML
        yaml_prompt = self._assemble_yaml(
            task_intent=task_intent,
            target_files=target_files,
            rag_context=rag_context,
            prohibited=prohibited,
            required=required,
            payload=payload,
        )

        # 4. Derivar confidence
        confidence = "HIGH" if rag_context else "MEDIUM"
        if warnings:
            confidence = "LOW"

        # 5. Salvar (TTL de 7 dias = 604800s)
        metadata = {
            "intent": task_intent,
            "target_files": target_files,
            "confidence": confidence,
        }
        prompt_id = await self._storage.save(
            project_id=project_id,
            content=yaml_prompt,
            metadata=metadata,
            ttl=3600 * 24 * 7,
        )

        return GeneratedPrompt(
            yaml_prompt=yaml_prompt,
            prompt_id=prompt_id,
            confidence=confidence,
            strategies_applied=["base_constraints", "rag_context"],
            warnings=warnings,
        )

    async def _build_constraints(
        self,
        session: AsyncSession,
        project_id: UUID,
        cfg: PromptStrategyConfig,
        payload: StrategyPayload,
    ) -> tuple[list[str], list[str]]:
        """Agrega constraints proibidos/obrigatórios. C_03: SELECT only."""
        stmt = (
            select(BusinessRule.technical_constraints)
            .where(BusinessRule.project_id == project_id)
            .order_by(BusinessRule.created_at.desc())
            .limit(_MAX_BUSINESS_RULES)
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()

        project_constraints: list[str] = []
        for constraints_list in rows:
            if constraints_list:
                project_constraints.extend(constraints_list)

        prohibited = (
            list(payload.prohibited) + list(cfg.extra_prohibited) + project_constraints
        )
        required = list(payload.required) + list(cfg.extra_required)

        return prohibited, required

    async def _fetch_rag_context(
        self,
        session: AsyncSession,
        project_id: UUID,
        task_intent: str,
        warnings: list[str],
    ) -> str:
        """Busca contexto relevante via cosine similarity (pgvector)."""
        try:
            embedding_service = EmbeddingService()
            embeddings = await embedding_service.embed_batch([task_intent])

            if not embeddings:
                warnings.append("rag_embedding_failed")
                return ""

            embedding_str = "[" + ",".join(str(v) for v in embeddings[0]) + "]"

            stmt = text(
                """
                SELECT title, content,
                       1 - (embedding <=> :query_embedding::vector) AS similarity
                FROM knowledge_documents
                WHERE project_id = :project_id
                  AND status = 'READY'
                  AND embedding IS NOT NULL
                ORDER BY embedding <=> :query_embedding::vector
                LIMIT :top_k
                """
            )

            result = await session.execute(
                stmt,
                {
                    "query_embedding": embedding_str,
                    "project_id": str(project_id),
                    "top_k": TOP_K_CONTEXT,
                },
            )
            rows = result.fetchall()

            if not rows:
                warnings.append("rag_no_documents")
                return ""

            context_blocks = [
                f"--- {row.title} (similarity: {row.similarity:.2f}) ---\n{row.content}"
                for row in rows
                if row.content
            ]
            return "\n\n".join(context_blocks)

        except Exception:  # noqa: BLE001
            logger.warning(
                "rag_context_fetch_failed", project_id=str(project_id)
            )
            warnings.append("rag_unavailable")
            return ""

    def _assemble_yaml(
        self,
        *,
        task_intent: str,
        target_files: list[str],
        rag_context: str,
        prohibited: list[str],
        required: list[str],
        payload: StrategyPayload,
    ) -> str:
        """Monta todos os componentes em um prompt YAML estruturado."""
        prompt: dict[str, object] = {}

        # System Block
        prompt["system"] = {
            "persona": payload.persona,
            "regras_constitucionais": {
                "proibido": prohibited,
                "obrigatorio": required,
            },
        }

        # Thinking Block
        prompt["raciocinio_obrigatorio"] = {
            "instrucao": (
                "ANTES de escrever qualquer código, produza um"
                " bloco <thinking> com: mapeamento de impacto,"
                " verificação de invariantes, fronteiras de transação,"
                " sequência de implementação."
            ),
        }

        # Execution Block
        execution: dict[str, object] = {
            "tarefa": task_intent,
            "arquivos_alvo": target_files,
        }

        if rag_context:
            execution["contexto_relevante"] = rag_context

        prompt["execucao"] = execution

        # Validation Block
        prompt["validacao"] = {
            "checklist_estatico": payload.checklist,
        }

        return yaml.dump(
            prompt,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            width=100,
        )

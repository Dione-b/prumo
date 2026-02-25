"""PromptGeneratorService — generates structured YAML prompts for LLM agents.

Combines project-specific business rules, knowledge graph context (local and
global), and best-practice patterns into a tiered YAML prompt. Supports
SIMPLE (entity-level) and COMPLEX (community-level + few-shot + skeletons)
tiers.

Key invariants honored:
  C_01: object.__setattr__ for frozen model mutations
  C_02: asyncio.to_thread for all synchronous Gemini SDK calls
  C_03: NEVER calls session.commit() — caller owns the transaction
"""

from __future__ import annotations

from uuid import UUID

import structlog
import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business_rule import BusinessRule
from app.schemas.knowledge import KnowledgeAnswer
from app.schemas.prompt_generator import (
    GeneratedPrompt,
    PromptStrategyConfig,
    PromptTier,
)
from app.services.graph_query_service import (
    global_query,
    local_query,
)

logger = structlog.get_logger()

# ── Module-Level Constants ──────────────────────────────────────────────────

_COMPLEX_KEYWORDS: frozenset[str] = frozenset({
    "refactor",
    "refatorar",
    "migrate",
    "migrar",
    "redesign",
    "architect",
    "integrate",
    "integrar",
    "pipeline",
    "multi-step",
    "multi-file",
    "graph-rag",
    "lightrag",
    "community",
    "extraction",
})

_TIER_STRATEGIES: dict[PromptTier, list[str]] = {
    PromptTier.SIMPLE: [
        "local_graph_context",
        "base_constraints",
        "thinking_enforcement",
    ],
    PromptTier.COMPLEX: [
        "local_graph_context",
        "global_graph_context",
        "base_constraints",
        "thinking_enforcement",
        "few_shot_examples",
        "code_skeletons",
        "validation_loop",
    ],
}

_BASE_PROHIBITED: list[str] = [
    "NEVER call session.commit() inside service or extractor methods"
    " — transaction boundary belongs to the task owner (C_03).",
    "NEVER use f-strings to inject dynamic content into LLM system"
    " instructions — use Gemini content Parts (Strategy 5).",
    "NEVER call genai.* synchronous methods directly in a coroutine"
    " — always wrap in asyncio.to_thread() (C_02).",
    "NEVER assign directly in a frozen model_validator"
    " — use object.__setattr__(self, field, value) (C_01).",
    "NEVER annotate Vector columns as Any"
    " — use list[float] | None with # type: ignore.",
    "NEVER pass List[UUID] to ANY(:param) in text() queries"
    " — use CAST(:param AS uuid[]) + str().",
]

_BASE_REQUIRED: list[str] = [
    "ALWAYS begin implementation with a <thinking> block covering:"
    " impact surface, invariant check, transaction boundaries,"
    " implementation order.",
    "ALWAYS wrap every synchronous Gemini SDK call in asyncio.to_thread().",
    "ALWAYS provide complete files with all imports explicit at the top.",
    "ALWAYS annotate all public method return types (mypy --strict).",
    "ALWAYS include updated_at in models that participate in"
    " cache invalidation.",
]

_FEW_SHOT_EXAMPLES: dict[str, dict[str, str]] = {
    "ASYNC_PATTERN": {
        "wrong": (
            "result = genai.embed_content(model=m, content=text)"
        ),
        "correct": (
            "result = await asyncio.to_thread("
            "genai.embed_content, model=m, content=text)"
        ),
        "rule": (
            "C_02 — Gemini SDK is synchronous;"
            " never block the event loop"
        ),
    },
    "TRANSACTION_BOUNDARY": {
        "wrong": (
            "await session.commit()  "
            "# inside EntityExtractor.extract_and_upsert"
        ),
        "correct": (
            "# commit lives in process_document_task"
            " after all branches succeed"
        ),
        "rule": "C_03 — service is never the transaction owner",
    },
    "PYDANTIC_C01": {
        "wrong": (
            "self.confidence = 'LOW'  "
            "# direct assign in frozen model_validator"
        ),
        "correct": (
            "object.__setattr__(self, 'confidence', 'LOW')"
        ),
        "rule": (
            "C_01 — Pydantic v2 frozen models"
            " forbid direct field assignment"
        ),
    },
    "UUID_ASYNCPG": {
        "wrong": (
            "session.execute("
            "text('ANY(:ids)'), {'ids': uuid_list})"
        ),
        "correct": (
            "session.execute(text('ANY(CAST(:ids AS uuid[]))'), "
            "{'ids': [str(u) for u in uuid_list]})"
        ),
        "rule": (
            "asyncpg cannot adapt list[UUID] in text()"
            " queries without explicit cast"
        ),
    },
}

# Maximum symbols per file for skeleton generation.
_MAX_SKELETONS_PER_FILE = 5

# Maximum business rules fetched per project.
_MAX_BUSINESS_RULES = 5


# ── Service Class ───────────────────────────────────────────────────────────


class PromptGeneratorService:
    """Generates structured YAML prompts for LLM agents.

    Orchestrates tier classification, constraint aggregation, graph context
    fetching, skeleton generation, and YAML assembly into a single pipeline.

    Does NOT instantiate any GenerativeModel at __init__ time — all LLM
    calls are deferred to the individual query engines.
    """

    async def generate_prompt(
        self,
        session: AsyncSession,
        project_id: UUID,
        task_intent: str,
        target_files: list[str],
        strategy_overrides: PromptStrategyConfig | None = None,
    ) -> GeneratedPrompt:
        """Generate a structured YAML prompt for LLM code generation.

        C_03: NEVER commits — caller owns the transaction.

        Args:
            session: Active async DB session (caller-owned).
            project_id: Target project UUID.
            task_intent: Natural-language description of the task.
            target_files: List of file paths the agent should modify.
            strategy_overrides: Optional config to tune generation.

        Returns:
            GeneratedPrompt with YAML content, tier, and quality metadata.
        """
        cfg = strategy_overrides or PromptStrategyConfig()
        warnings: list[str] = []

        # 1. Classify tier.
        tier = self._classify_tier(task_intent, target_files)
        if cfg.force_tier is not None:
            tier = cfg.force_tier

        # 2. Build constraints from project rules + base.
        prohibited, required = await self._build_constraints(
            session, project_id, cfg
        )

        # 3. Fetch local graph context.
        local_answer = await self._fetch_local_context(
            session, project_id, task_intent, cfg.k_seeds, warnings
        )

        # 4. Fetch global context (COMPLEX tier only).
        global_answer: KnowledgeAnswer | None = None
        if tier == PromptTier.COMPLEX:
            global_answer = await self._fetch_global_context(
                session, project_id, task_intent, warnings
            )

        # 5. Build skeletons (COMPLEX + enabled).
        skeletons: list[dict[str, str]] = []
        if (
            tier == PromptTier.COMPLEX
            and cfg.include_skeletons
        ):
            skeletons = self._build_skeletons(
                target_files, local_answer
            )

        # 6. Assemble YAML.
        yaml_prompt = self._assemble_yaml(
            tier=tier,
            task_intent=task_intent,
            target_files=target_files,
            local_answer=local_answer,
            global_answer=global_answer,
            prohibited=prohibited,
            required=required,
            skeletons=skeletons,
            cfg=cfg,
        )

        # 7. Derive confidence.
        confidence = self._derive_confidence(
            local_answer, global_answer, tier, warnings
        )

        # 8. Collect citations from graph answers.
        all_citations = list(local_answer.citations)
        if global_answer:
            all_citations.extend(global_answer.citations)

        strategies = list(_TIER_STRATEGIES.get(tier, []))

        # 9. Return — model_validator auto-enforces confidence downgrade.
        return GeneratedPrompt(
            yaml_prompt=yaml_prompt,
            tier=tier,
            strategies_applied=strategies,
            confidence=confidence,
            graph_citations=all_citations,
            warnings=warnings,
        )

    # ── Private Methods ─────────────────────────────────────────────────────

    def _classify_tier(
        self,
        task_intent: str,
        target_files: list[str],
    ) -> PromptTier:
        """Classify the prompt tier based on intent keywords and file count.

        O(n) keywords scan — zero LLM calls.
        """
        intent_lower = task_intent.lower()

        if any(kw in intent_lower for kw in _COMPLEX_KEYWORDS):
            return PromptTier.COMPLEX

        if len(target_files) > 1:
            return PromptTier.COMPLEX

        return PromptTier.SIMPLE

    async def _build_constraints(
        self,
        session: AsyncSession,
        project_id: UUID,
        cfg: PromptStrategyConfig,
    ) -> tuple[list[str], list[str]]:
        """Aggregate prohibited and required constraints.

        C_03: SELECT only — NEVER commits.

        Merges base rules + project-specific technical constraints
        + caller-provided extras.
        """
        stmt = (
            select(BusinessRule.technical_constraints)
            .where(BusinessRule.project_id == project_id)
            .order_by(BusinessRule.created_at.desc())
            .limit(_MAX_BUSINESS_RULES)
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()

        # Flatten project constraints into a single list.
        project_constraints: list[str] = []
        for constraints_list in rows:
            if constraints_list:
                project_constraints.extend(constraints_list)

        prohibited = (
            list(_BASE_PROHIBITED)
            + list(cfg.extra_prohibited)
            + project_constraints
        )
        required = list(_BASE_REQUIRED) + list(cfg.extra_required)

        return prohibited, required

    async def _fetch_local_context(
        self,
        session: AsyncSession,
        project_id: UUID,
        task_intent: str,
        k_seeds: int,
        warnings: list[str],
    ) -> KnowledgeAnswer:
        """Fetch entity-level context from the knowledge graph.

        C_03: delegates to local_query which does SELECT only.

        Falls back to an empty KnowledgeAnswer on any failure,
        appending 'graph_local_unavailable' to warnings.
        """
        try:
            answer = await local_query(session, project_id, task_intent)

            if (
                answer.confidence_level == "LOW"
                and not answer.citations
            ):
                warnings.append("graph_local_unavailable")

            return answer

        except Exception:  # noqa: BLE001
            logger.warning(
                "prompt_gen_local_context_failed",
                project_id=str(project_id),
            )
            warnings.append("graph_local_unavailable")
            return KnowledgeAnswer(
                answer="",
                confidence_level="LOW",
                citations=[],
            )

    async def _fetch_global_context(
        self,
        session: AsyncSession,
        project_id: UUID,
        task_intent: str,
        warnings: list[str],
    ) -> KnowledgeAnswer | None:
        """Fetch community-level context from the knowledge graph.

        C_03: delegates to global_query which does SELECT only.

        Returns None if the global context is unavailable or low quality.
        """
        try:
            answer = await global_query(
                session, project_id, task_intent
            )

            if answer.confidence_level == "LOW":
                warnings.append("graph_global_unavailable")
                return None

            return answer

        except Exception:  # noqa: BLE001
            logger.warning(
                "prompt_gen_global_context_failed",
                project_id=str(project_id),
            )
            warnings.append("graph_global_unavailable")
            return None

    def _build_skeletons(
        self,
        target_files: list[str],
        local_answer: KnowledgeAnswer,
    ) -> list[dict[str, str]]:
        """Generate async def skeletons from graph citations.

        Extracts entity names from citations and produces skeleton
        signatures with C_03 compliance docstrings. Caps at 5 symbols
        per file to avoid prompt overflow.
        """
        entity_names: list[str] = []
        for citation in local_answer.citations:
            source = citation.source
            if source and not source.startswith("doc:"):
                entity_names.append(source)

        if not entity_names:
            return []

        # Deduplicate while preserving order.
        seen: set[str] = set()
        unique_names: list[str] = []
        for name in entity_names:
            if name not in seen:
                seen.add(name)
                unique_names.append(name)

        skeletons: list[dict[str, str]] = []

        for target_file in target_files:
            file_symbols = unique_names[:_MAX_SKELETONS_PER_FILE]
            for symbol in file_symbols:
                # Normalize to snake_case for function naming.
                func_name = (
                    symbol.lower()
                    .replace(" ", "_")
                    .replace("-", "_")
                    .replace(".", "_")
                )
                skeleton = {
                    "file": target_file,
                    "symbol": symbol,
                    "skeleton": (
                        f"async def {func_name}(\n"
                        f"    session: AsyncSession,\n"
                        f"    # ... params\n"
                        f") -> ...:\n"
                        f'    """Handle {symbol}.\n'
                        f"\n"
                        f"    C_03: NEVER commits — caller owns"
                        f" the transaction.\n"
                        f'    """\n'
                        f"    ..."
                    ),
                }
                skeletons.append(skeleton)

        return skeletons

    def _assemble_yaml(
        self,
        *,
        tier: PromptTier,
        task_intent: str,
        target_files: list[str],
        local_answer: KnowledgeAnswer,
        global_answer: KnowledgeAnswer | None,
        prohibited: list[str],
        required: list[str],
        skeletons: list[dict[str, str]],
        cfg: PromptStrategyConfig,
    ) -> str:
        """Assemble all components into a structured YAML prompt.

        Structure:
          system_block    → persona + regras constitucionais (Strategy 5)
          thinking_block  → raciocínio obrigatório (Strategy 2)
          execution_block → tarefa + arquivos + contexto
          few_shot_block  → exemplos (Strategy 8, COMPLEX only)
          validation_block → checklist estático + dinâmico
        """
        prompt: dict[str, object] = {}

        # ── System Block (Strategy 5: isolated) ──
        prompt["system"] = {
            "persona": (
                "Senior Backend Engineer specializing in"
                " async RAG pipelines. Stack: FastAPI ·"
                " SQLAlchemy 2.0 async · Pydantic v2 strict"
                " · pgvector · Gemini SDK."
            ),
            "regras_constitucionais": {
                "proibido": prohibited,
                "obrigatorio": required,
            },
        }

        # ── Thinking Block (Strategy 2: mandatory) ──
        prompt["raciocinio_obrigatorio"] = {
            "instrucao": (
                "ANTES de escrever qualquer código, produza um"
                " bloco <thinking> com: mapeamento de impacto,"
                " verificação de invariantes C_01/C_02/C_03,"
                " fronteiras de transação, sequência de"
                " implementação."
            ),
        }

        # ── Execution Block ──
        execution: dict[str, object] = {
            "tarefa": task_intent,
            "arquivos_alvo": target_files,
        }

        if local_answer.answer:
            execution["contexto_local"] = {
                "conteudo": local_answer.answer,
                "confidence": local_answer.confidence_level,
                "citacoes": [
                    {
                        "snippet": c.snippet,
                        "source": c.source or "unknown",
                    }
                    for c in local_answer.citations
                ],
            }

        if global_answer and global_answer.answer:
            execution["contexto_arquitetural"] = {
                "conteudo": global_answer.answer,
                "confidence": global_answer.confidence_level,
            }

        if skeletons:
            execution["esqueletos_sugeridos"] = skeletons

        prompt["execucao"] = execution

        # ── Few-Shot Block (Strategy 8: COMPLEX only) ──
        if (
            tier == PromptTier.COMPLEX
            and cfg.include_few_shot
        ):
            prompt["exemplos_few_shot"] = _FEW_SHOT_EXAMPLES

        # ── Validation Block ──
        prompt["validacao"] = {
            "checklist_estatico": [
                "Nenhum session.commit() em services (C_03)",
                "Todo genai.* em asyncio.to_thread() (C_02)",
                "model_validator frozen usa"
                " object.__setattr__ (C_01)",
                "YAML output parseável por yaml.safe_load",
            ],
        }

        return yaml.dump(
            prompt,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            width=100,
        )

    def _derive_confidence(
        self,
        local: KnowledgeAnswer,
        global_ans: KnowledgeAnswer | None,
        tier: PromptTier,
        warnings: list[str],
    ) -> str:
        """Derive overall confidence from graph answers and warnings.

        Rules (in order of priority):
          1. Both local + global unavailable → LOW
          2. Local unavailable only → MEDIUM
          3. COMPLEX + global is None → MEDIUM
          4. local HIGH → HIGH
          5. local MEDIUM → MEDIUM
          6. Fallback → LOW
        """
        local_unavailable = "graph_local_unavailable" in warnings
        global_unavailable = "graph_global_unavailable" in warnings

        if local_unavailable and global_unavailable:
            return "LOW"

        if local_unavailable:
            return "MEDIUM"

        if tier == PromptTier.COMPLEX and global_ans is None:
            return "MEDIUM"

        if local.confidence_level == "HIGH":
            return "HIGH"

        if local.confidence_level == "MEDIUM":
            return "MEDIUM"

        return "LOW"

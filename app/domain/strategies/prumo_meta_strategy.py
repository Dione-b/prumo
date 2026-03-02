from __future__ import annotations

from app.domain.strategies.prompt_strategy import IPromptStrategy, StrategyPayload


class PrumoMetaStrategy(IPromptStrategy):
    """Estratégia exclusiva para o próprio orquestrador Prumo (Python/FastAPI)."""

    def get_payload(self) -> StrategyPayload:
        return StrategyPayload(
            persona=(
                "Senior Backend Engineer specializing in async RAG pipelines. "
                "Stack: FastAPI · SQLAlchemy 2.0 async · Pydantic v2 strict · "
                "pgvector · Gemini SDK."
            ),
            prohibited=[
                "NEVER call session.commit() inside service or extractor"
                " methods — transaction boundary belongs to the task"
                " owner (C_03).",
                "NEVER use f-strings to inject dynamic content into LLM"
                " system instructions — use Gemini content Parts"
                " (Strategy 5).",
                "NEVER call genai.* synchronous methods directly in a"
                " coroutine — always wrap in asyncio.to_thread() (C_02).",
                "NEVER assign directly in a frozen model_validator"
                " — use object.__setattr__(self, field, value) (C_01).",
                "NEVER annotate Vector columns as Any"
                " — use list[float] | None with # type: ignore.",
                "NEVER pass List[UUID] to ANY(:param) in text() queries"
                " — use CAST(:param AS uuid[]) + str().",
            ],
            required=[
                "ALWAYS begin implementation with a <thinking> block"
                " covering: impact surface, invariant check, transaction"
                " boundaries, implementation order.",
                "ALWAYS wrap every synchronous Gemini SDK call in asyncio.to_thread().",
                "ALWAYS provide complete files with all imports explicit at the top.",
                "ALWAYS annotate all public method return types (mypy --strict).",
            ],
            few_shot_examples={
                "ASYNC_PATTERN": {
                    "wrong": ("result = genai.embed_content(model=m, content=text)"),
                    "correct": (
                        "result = await asyncio.to_thread("
                        "genai.embed_content, model=m, content=text)"
                    ),
                    "rule": (
                        "C_02 — Gemini SDK is synchronous; never block the event loop"
                    ),
                },
                "TRANSACTION_BOUNDARY": {
                    "wrong": ("await session.commit()  # inside service"),
                    "correct": ("# commit lives in the router/worker, owner of tx"),
                    "rule": ("C_03 — service is never the transaction owner"),
                },
            },
            checklist=[
                "Nenhum session.commit() em services (C_03)",
                "Todo genai.* em asyncio.to_thread() (C_02)",
                "model_validator frozen usa object.__setattr__ (C_01)",
                "YAML output parseável por yaml.safe_load",
            ],
        )

    def generate_skeleton(self, target_file: str, symbol: str) -> str:
        func_name = symbol.lower().replace(" ", "_").replace("-", "_").replace(".", "_")
        return (
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
        )

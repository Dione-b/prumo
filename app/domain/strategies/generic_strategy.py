from __future__ import annotations

from app.domain.strategies.prompt_strategy import IPromptStrategy, StrategyPayload


class GenericStrategy(IPromptStrategy):
    """Fallback — Strategy limpa baseada apenas em Clean Architecture."""

    def get_payload(self) -> StrategyPayload:
        return StrategyPayload(
            persona=(
                "Senior Software Engineer acting as a mentor in Clean Code, "
                "SOLID, and software architecture."
            ),
            prohibited=[
                "NEVER leave large duplicated blocks — use DRY principles.",
                "NEVER use generic Exceptions unhandled.",
                "NEVER mix IO (DB, HTTP) directly in pure domain logic.",
            ],
            required=[
                "ALWAYS apply Single Responsibility Principle to classes/functions.",
                "ALWAYS provide clear docstrings for public interfaces.",
                "ALWAYS keep testing considerations in mind (Dependency Injection).",
            ],
            few_shot_examples={},
            checklist=[
                "Os princípios SOLID estão respeitados?",
                "Código legível, modular e claro?",
                "Responsabilidades segregadas (Clean Architecture)?",
                "YAML output parseável por yaml.safe_load",
            ],
        )

    def generate_skeleton(self, target_file: str, symbol: str) -> str:
        func_name = symbol.lower().replace(" ", "_").replace("-", "_").replace(".", "_")
        return (
            f"def {func_name}(/* params */):\n"
            f'    """Handle {symbol}."""\n'
            f"    # TODO: implement logic\n"
            f"    pass"
        )

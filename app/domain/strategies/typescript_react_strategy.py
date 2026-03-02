from __future__ import annotations

from app.domain.strategies.prompt_strategy import IPromptStrategy, StrategyPayload


class TypeScriptReactStrategy(IPromptStrategy):
    """Estratégia para projetos Frontend (React, Next.js, TS)."""

    def get_payload(self) -> StrategyPayload:
        return StrategyPayload(
            persona=(
                "Senior Frontend/Fullstack Engineer specializing in"
                " React, Next.js, and TypeScript. Strict ESLint +"
                " Prettier. Focus on performance, clean component"
                " boundaries, and UX."
            ),
            prohibited=[
                "NEVER use `any` type — prefer `unknown` +"
                " type guards or strict typing.",
                "NEVER mutate props directly — treat data as immutable.",
                "NEVER nest excessive hooks inside loops or"
                " conditions (Rules of Hooks).",
                "NEVER export default unless specifically"
                " required by a framework routing convention.",
            ],
            required=[
                "ALWAYS use strict TypeScript (`strict: true` in tsconfig).",
                "ALWAYS validate external API data with Zod (or similar) schemas.",
                "ALWAYS leverage React.memo and useCallback"
                " judiciously to avoid unnecessary renders.",
                "ALWAYS separate state management from dumb presentational components.",
            ],
            few_shot_examples={},
            checklist=[
                "Sem uso de `any` em código novo?",
                "Todos os hooks obedecem às Rules of Hooks?",
                "Separação clara entre Smart e Dumb Components?",
                "YAML output parseável por yaml.safe_load",
            ],
        )

    def generate_skeleton(self, target_file: str, symbol: str) -> str:
        clean = symbol.replace(" ", "").replace("-", "")
        return (
            f"export const {clean} ="
            f" (props: {clean}Props) => {{\n"
            f"    // Handle {symbol}.\n"
            f"    return (\n"
            f"        <div>\n"
            f"            {{/* Implementation */}}\n"
            f"        </div>\n"
            f"    );\n"
            f"}};"
        )

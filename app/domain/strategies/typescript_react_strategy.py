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

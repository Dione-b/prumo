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

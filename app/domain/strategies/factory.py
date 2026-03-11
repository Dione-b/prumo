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

from typing import Any

from app.domain.strategies.generic_strategy import GenericStrategy
from app.domain.strategies.prompt_strategy import IPromptStrategy
from app.domain.strategies.prumo_meta_strategy import PrumoMetaStrategy
from app.domain.strategies.rust_soroban_strategy import RustSorobanStrategy
from app.domain.strategies.typescript_react_strategy import TypeScriptReactStrategy

_TS_KEYWORDS = ("react", "next.js", "typescript", "frontend", "web3")
_PRUMO_KEYWORDS = ("fastapi", "sqlalchemy", "pydantic", "prumo")
_RUST_KEYWORDS = ("soroban", "rust", "cargo", "stellar")

VALID_STACKS = {"generic", "typescript", "prumo", "rust"}


class StrategyResolver:
    """Factory that returns the appropriate IPromptStrategy."""

    @staticmethod
    def is_valid_stack(stack: str) -> bool:
        """Check if a project stack parameter is recognized."""
        return stack.lower() in VALID_STACKS

    @staticmethod
    def resolve(
        config_json: dict[str, Any] | None,
        description: str | None,
    ) -> IPromptStrategy:
        """Instantiates and returns the concrete Strategy.

        Args:
            config_json: Extracted settings from Project model (requires 'stack').
            description: Narrative text of the Project model (for fallback inference).

        Returns:
            A specific implementation of IPromptStrategy.
            Defaults to GenericStrategy if stack is omitted or unknown.
        """
        strategy_key = "generic"

        if config_json and "stack" in config_json:
            stack_val = str(config_json["stack"]).lower()
            if StrategyResolver.is_valid_stack(stack_val):
                strategy_key = stack_val
        elif description:
            desc_lower = description.lower()
            if any(kw in desc_lower for kw in _TS_KEYWORDS):
                strategy_key = "typescript"
            elif any(kw in desc_lower for kw in _PRUMO_KEYWORDS):
                strategy_key = "prumo"
            elif any(kw in desc_lower for kw in _RUST_KEYWORDS):
                strategy_key = "rust"

        if strategy_key == "prumo":
            return PrumoMetaStrategy()
        if strategy_key == "typescript":
            return TypeScriptReactStrategy()
        if strategy_key == "rust":
            return RustSorobanStrategy()

        return GenericStrategy()

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

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class StrategyPayload:
    """Read-only container for strategy-specific prompt components."""

    persona: str
    prohibited: list[str]
    required: list[str]
    few_shot_examples: dict[str, dict[str, str]]
    checklist: list[str]


class IPromptStrategy(Protocol):
    """Protocol for dynamic prompt generation rules based on target tech stack."""

    def get_payload(self) -> StrategyPayload:
        """Returns the specific strategy payload for YAML synthesis."""
        ...

    def generate_skeleton(self, target_file: str, symbol: str) -> str:
        """Generates a code skeleton string for the provided language."""
        ...

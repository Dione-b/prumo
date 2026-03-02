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

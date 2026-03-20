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


"""Tests for PromptGenerator schemas."""

import pytest

from app.schemas.prompt_generator import GeneratedPrompt, PromptStrategyConfig


def test_generated_prompt_is_frozen() -> None:
    # Arrange
    prompt = GeneratedPrompt(
        yaml_prompt="test: true",
        strategies_applied=[],
        confidence="HIGH",
    )

    # Act / Assert
    with pytest.raises(Exception):  # noqa: B017
        prompt.yaml_prompt = "changed"  # type: ignore[misc]


def test_generated_prompt_no_warnings_keeps_confidence() -> None:
    # Arrange / Act
    prompt = GeneratedPrompt(
        yaml_prompt="test: true",
        strategies_applied=[],
        confidence="HIGH",
        warnings=[],
    )

    # Assert
    assert prompt.confidence == "HIGH"


def test_generated_prompt_low_confidence_preserved() -> None:
    # Arrange / Act
    prompt = GeneratedPrompt(
        yaml_prompt="test: true",
        strategies_applied=[],
        confidence="LOW",
        warnings=["rag_no_documents"],
    )

    # Assert
    assert prompt.confidence == "LOW"


def test_strategy_config_defaults() -> None:
    # Act
    cfg = PromptStrategyConfig()

    # Assert
    assert cfg.extra_prohibited == []
    assert cfg.extra_required == []


def test_strategy_config_with_overrides() -> None:
    # Act
    cfg = PromptStrategyConfig(
        extra_prohibited=["no globals"],
        extra_required=["use typing"],
    )

    # Assert
    assert cfg.extra_prohibited == ["no globals"]
    assert cfg.extra_required == ["use typing"]

"""Tests for PromptGenerator schemas and tier classification."""

from unittest.mock import AsyncMock

import pytest

from app.schemas.prompt_generator import (
    GeneratedPrompt,
    PromptStrategyConfig,
    PromptTier,
)
from app.services.prompt_generator import PromptGeneratorService

# ── Schema Tests ────────────────────────────────────────────────────────────


def test_generated_prompt_high_confidence_with_local_warning_downgrades() -> None:
    """C_01: HIGH + graph_local_unavailable → MEDIUM."""
    # Arrange / Act
    prompt = GeneratedPrompt(
        yaml_prompt="test: true",
        tier=PromptTier.SIMPLE,
        strategies_applied=["local_graph_context"],
        confidence="HIGH",
        warnings=["graph_local_unavailable"],
    )

    # Assert
    assert prompt.confidence == "MEDIUM"


def test_generated_prompt_two_blocking_warnings_downgrades_to_low() -> None:
    """C_01: 2+ blocking warnings → LOW."""
    # Arrange / Act
    prompt = GeneratedPrompt(
        yaml_prompt="test: true",
        tier=PromptTier.COMPLEX,
        strategies_applied=[],
        confidence="HIGH",
        warnings=[
            "graph_local_unavailable",
            "graph_global_unavailable",
        ],
    )

    # Assert
    assert prompt.confidence == "LOW"


def test_generated_prompt_no_warnings_keeps_confidence() -> None:
    # Arrange / Act
    prompt = GeneratedPrompt(
        yaml_prompt="test: true",
        tier=PromptTier.SIMPLE,
        strategies_applied=[],
        confidence="HIGH",
        warnings=[],
    )

    # Assert
    assert prompt.confidence == "HIGH"


def test_generated_prompt_medium_with_one_warning_stays_medium() -> None:
    """C_01: MEDIUM + 1 warning → stays MEDIUM (only HIGH is downgraded)."""
    # Arrange / Act
    prompt = GeneratedPrompt(
        yaml_prompt="test: true",
        tier=PromptTier.SIMPLE,
        strategies_applied=[],
        confidence="MEDIUM",
        warnings=["graph_local_unavailable"],
    )

    # Assert
    assert prompt.confidence == "MEDIUM"


def test_generated_prompt_is_frozen() -> None:
    # Arrange
    prompt = GeneratedPrompt(
        yaml_prompt="test: true",
        tier=PromptTier.SIMPLE,
        strategies_applied=[],
        confidence="HIGH",
    )

    # Act / Assert
    with pytest.raises(Exception):  # noqa: B017
        prompt.yaml_prompt = "changed"  # type: ignore[misc]


def test_strategy_config_defaults() -> None:
    # Act
    cfg = PromptStrategyConfig()

    # Assert
    assert cfg.force_tier is None
    assert cfg.k_seeds == 10
    assert cfg.include_few_shot is True
    assert cfg.include_skeletons is True
    assert cfg.extra_prohibited == []
    assert cfg.extra_required == []


def test_strategy_config_k_seeds_bounds() -> None:
    # Act / Assert — k_seeds min
    with pytest.raises(Exception):  # noqa: B017
        PromptStrategyConfig(k_seeds=0)

    # Act / Assert — k_seeds max
    with pytest.raises(Exception):  # noqa: B017
        PromptStrategyConfig(k_seeds=51)


# ── Tier Classification Tests ───────────────────────────────────────────────

_service = PromptGeneratorService(storage=AsyncMock())


def test_classify_tier_simple_single_file() -> None:
    # Act
    tier = _service._classify_tier("add logging", ["app/main.py"])

    # Assert
    assert tier == PromptTier.SIMPLE


def test_classify_tier_complex_keyword() -> None:
    # Act
    tier = _service._classify_tier(
        "refactor process_document_task",
        ["app/services/knowledge_gemini.py"],
    )

    # Assert
    assert tier == PromptTier.COMPLEX


def test_classify_tier_complex_multiple_files() -> None:
    # Act
    tier = _service._classify_tier(
        "add logging",
        ["app/services/a.py", "app/services/b.py"],
    )

    # Assert
    assert tier == PromptTier.COMPLEX


def test_classify_tier_complex_keyword_case_insensitive() -> None:
    # Act
    tier = _service._classify_tier(
        "INTEGRATE new pipeline",
        ["app/services/x.py"],
    )

    # Assert
    assert tier == PromptTier.COMPLEX

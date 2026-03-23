"""Unit tests for the exporter.

Mock LLM clients via unittest.mock.patch.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from prumo.crawler import Page
from prumo.exporter import MAX_CONTENT_CHARS, SYSTEM_PROMPT, export_llms_txt

SAMPLE_PAGES = [
    Page(
        title="Installation",
        url="https://docs.example.com/install",
        content="Run pip install example to get started.",
    ),
    Page(
        title="Quick Start",
        url="https://docs.example.com/quickstart",
        content="Create your first app with example init.",
    ),
]

LLM_RESPONSE = """# Example

> A library for doing example things.

## Getting Started
- [Installation](https://docs.example.com/install): How to install the package.
- [Quick Start](https://docs.example.com/quickstart): Create your first application.
"""


class TestExportGemini:
    """Tests integration with Gemini (mocked)."""

    def test_gemini_returns_llm_response_unmodified(self) -> None:
        # Arrange — mock import and call
        with patch.dict("prumo.exporter._PROVIDER_CALLERS", {"gemini": MagicMock(return_value=LLM_RESPONSE)}):
            # Act
            result = export_llms_txt(SAMPLE_PAGES, "gemini", "fake-key")

        # Assert — returned string must be exactly what the LLM returned
        assert result == LLM_RESPONSE


class TestExportClaude:
    """Tests integration with Claude (mocked)."""

    def test_claude_returns_llm_response_unmodified(self) -> None:
        # Arrange
        with patch.dict("prumo.exporter._PROVIDER_CALLERS", {"claude": MagicMock(return_value=LLM_RESPONSE)}):
            # Act
            result = export_llms_txt(SAMPLE_PAGES, "claude", "fake-key")

        # Assert
        assert result == LLM_RESPONSE


class TestExportPromptConstruction:
    """Tests that the prompt is constructed correctly."""

    def test_prompt_contains_all_pages(self) -> None:
        # Arrange
        captured_prompt: list[str] = []

        def fake_gemini(prompt: str, system: str, api_key: str) -> str:
            captured_prompt.append(prompt)
            return LLM_RESPONSE

        with patch.dict("prumo.exporter._PROVIDER_CALLERS", {"gemini": fake_gemini}):
            # Act
            export_llms_txt(SAMPLE_PAGES, "gemini", "fake-key")

        # Assert — prompt must contain titles and URLs of all pages
        prompt = captured_prompt[0]
        assert "Installation" in prompt
        assert "Quick Start" in prompt
        assert "https://docs.example.com/install" in prompt
        assert "https://docs.example.com/quickstart" in prompt

    def test_system_prompt_contains_rules(self) -> None:
        """The system prompt must contain formatting rules."""
        # Assert
        assert "llms.txt" in SYSTEM_PROMPT
        assert "Markdown" in SYSTEM_PROMPT
        assert "Do NOT invent content" in SYSTEM_PROMPT


class TestExportTruncation:
    """Tests warning when content exceeds token limit."""

    def test_truncation_warning_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        # Arrange — create pages with content that exceeds limit
        big_content = "x" * (MAX_CONTENT_CHARS + 1000)
        base_url = "https://docs.example.com/p"
        big_pages = [
            Page(
                title=f"Page {i}",
                url=f"{base_url}{i}",
                content=big_content,
            )
            for i in range(5)
        ]

        with patch.dict("prumo.exporter._PROVIDER_CALLERS", {"gemini": MagicMock(return_value="# Result")}):
            with caplog.at_level(logging.WARNING):
                # Act
                export_llms_txt(big_pages, "gemini", "fake-key")

        # Assert — truncation warning must appear in logs
        assert any("truncated" in record.message.lower() for record in caplog.records)


class TestExportEmptyPages:
    """Tests that an empty list returns an empty string."""

    def test_empty_pages_returns_empty_string(self) -> None:
        # Act
        result = export_llms_txt([], "gemini", "fake-key")

        # Assert
        assert result == ""


class TestExportInvalidProvider:
    """Tests that an invalid provider raises ValueError."""

    def test_invalid_provider_raises_value_error(self) -> None:
        # Act / Assert
        with pytest.raises(ValueError, match="Unsupported provider"):
            export_llms_txt(SAMPLE_PAGES, "openai", "fake-key")  # type: ignore[arg-type]

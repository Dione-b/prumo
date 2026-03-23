"""Exporter that converts documentation pages into llms.txt via an LLM.

Receives the page list from the crawler, builds a consolidated prompt,
calls the chosen LLM (Gemini or Claude), and returns the raw string.
"""

from __future__ import annotations

import logging
from typing import Literal

from prumo.crawler import Page

logger = logging.getLogger(__name__)

# ~80k tokens ≈ 320k characters (conservative estimate of 4 chars/token)
MAX_CONTENT_CHARS = 320_000

SYSTEM_PROMPT = (
    "You are a technical documentation summarizer. "
    "Your task is to convert a list of documentation pages "
    "into a well-structured llms.txt file.\n\n"
    "Rules:\n"
    "1. Output ONLY valid Markdown. "
    "No preamble, no explanation, no code fences.\n"
    "2. Start with: # {Project Name}\\n\\n"
    "> {One-line description}\\n\\n\n"
    "3. Group pages into logical sections "
    "using ## headings.\n"
    "4. Each page becomes one list item: "
    "- [{Title}]({url}): "
    "{One sentence describing what this page covers.}\n"
    "5. Do NOT invent content. "
    "Only use what is provided.\n"
    "6. Do NOT include changelog, release notes, "
    "or API dump pages.\n"
    "7. Keep descriptions concise — "
    "one sentence per page, maximum 15 words."
)


def _build_pages_content(pages: list[Page]) -> str:
    """Builds the pages content string for the prompt, truncating if necessary."""
    parts: list[str] = []
    total_chars = 0

    for i, page in enumerate(pages):
        entry = (
            f"## Page {i + 1}: {page.title}\n"
            f"URL: {page.url}\n\n"
            f"{page.content}\n\n---\n"
        )
        total_chars += len(entry)

        if total_chars > MAX_CONTENT_CHARS:
            logger.warning(
                "Content truncated: %d of %d pages included (limit ~80k tokens)",
                i,
                len(pages),
            )
            break

        parts.append(entry)

    return "".join(parts)


def _call_gemini(prompt: str, system: str, api_key: str) -> str:
    """Calls the Google Gemini API."""
    import google.generativeai as genai

    genai.configure(api_key=api_key)  # type: ignore[attr-defined]
    model = genai.GenerativeModel(  # type: ignore[attr-defined]
        model_name="gemini-2.5-flash",
        system_instruction=system,
    )
    response = model.generate_content(prompt)
    return response.text  # type: ignore[no-any-return]


def _call_claude(prompt: str, system: str, api_key: str) -> str:
    """Calls the Anthropic Claude API."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8192,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    # Response contains content blocks; extract the text from the first one
    return message.content[0].text  # type: ignore[union-attr]


def export_llms_txt(
    pages: list[Page],
    provider: Literal["gemini", "claude"],
    api_key: str,
) -> str:
    """Exports documentation pages to llms.txt format via an LLM.

    Args:
        pages: List of pages with title, URL, and content.
        provider: LLM provider ('gemini' or 'claude').
        api_key: API key for the provider.

    Returns:
        Markdown-formatted string in llms.txt format.

    Raises:
        ValueError: If the provider is not supported.
    """
    if not pages:
        return ""

    pages_content = _build_pages_content(pages)
    prompt = f"Here are the documentation pages:\n\n{pages_content}"

    if provider == "gemini":
        return _call_gemini(prompt, SYSTEM_PROMPT, api_key)
    if provider == "claude":
        return _call_claude(prompt, SYSTEM_PROMPT, api_key)

    msg = f"Unsupported provider: {provider}"
    raise ValueError(msg)

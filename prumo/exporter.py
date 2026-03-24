"""Exporter that converts documentation pages into llms.md via an LLM.

Receives the page list from the crawler, builds a consolidated prompt,
calls the chosen LLM (Gemini or Claude), and returns the raw string.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Literal

from prumo.models import Page

logger = logging.getLogger(__name__)

# ~80k tokens ≈ 320k characters (conservative estimate of 4 chars/token)
MAX_CONTENT_CHARS = 320_000

Provider = Literal["gemini", "claude"]

SYSTEM_PROMPT = """\
You are a technical documentation converter. Your task is to take crawled \
documentation pages and produce a single, clean, well-structured Markdown document.

Rules:
1. Output ONLY valid Markdown. No preamble, no explanation, no code fences wrapping the output.
2. Start with a level-1 heading for the project name.
3. Below the heading, add a blockquote with a one-line project description.
4. Preserve ALL content from the source pages — headings, paragraphs, lists, links, bold, and code references.
5. Do NOT summarize or omit information from the source pages.
6. Use the original heading hierarchy (##, ###, etc.) from each page whenever possible.
7. Preserve links in [text](url) format.
8. When combining multiple pages, use a horizontal rule (---) between pages.
9. Remove duplicated navigation text, breadcrumbs, or repeated headers/footers that appear across pages.
10. Do NOT invent content. Only use what is provided.\
"""


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

        if total_chars + len(entry) > MAX_CONTENT_CHARS:
            logger.warning(
                "Content truncated: %d of %d pages included (limit ~80k tokens)",
                i,
                len(pages),
            )
            break

        parts.append(entry)
        total_chars += len(entry)

    return "".join(parts)


def _call_gemini(prompt: str, system: str, api_key: str) -> str:
    """Calls the Google Gemini API."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=system),
    )
    return response.text or ""


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
    return message.content[0].text  # type: ignore[union-attr]


ProviderCaller = Callable[[str, str, str], str]

_PROVIDER_CALLERS: dict[str, ProviderCaller] = {
    "gemini": _call_gemini,
    "claude": _call_claude,
}


def export_llms_txt(pages: list[Page], provider: Provider, api_key: str) -> str:
    """Exports documentation pages to llms.md format via an LLM.

    Args:
        pages: List of pages with title, URL, and content.
        provider: LLM provider ('gemini' or 'claude').
        api_key: API key for the provider.

    Returns:
        Markdown-formatted string in llms.md format.

    Raises:
        ValueError: If the provider is not supported.
    """
    if not pages:
        return ""

    caller = _PROVIDER_CALLERS.get(provider)
    if caller is None:
        raise ValueError(f"Unsupported provider: {provider}")

    prompt = f"Here are the documentation pages:\n\n{_build_pages_content(pages)}"
    return caller(prompt, SYSTEM_PROMPT, api_key)
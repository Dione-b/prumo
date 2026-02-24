import json
import re
from typing import Any

from app.core.exceptions import SanitizationError


def sanitize_llm_json(raw_text: str) -> dict[str, Any]:
    """Remove formatting artifacts that LLMs inject due to alignment bias.

    Runs BEFORE json.loads() — never trust raw LLM output.
    """
    # Strip markdown fenced code blocks: ```json ... ``` or ``` ... ```
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw_text).strip()

    try:
        result: dict[str, Any] = json.loads(cleaned)
        return result
    except json.JSONDecodeError as e:
        raise SanitizationError(
            f"Failed to parse JSON after sanitization. Error: {e}\n"
            f"Received text: {cleaned[:200]}"
        ) from e

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


import io
import json
import re
from typing import Any

import pypdf

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


def normalize_keys(data: Any) -> Any:
    """Recursively converts all dictionary keys to lowercase."""
    if isinstance(data, dict):
        return {str(k).lower(): normalize_keys(v) for k, v in data.items()}
    if isinstance(data, list):
        return [normalize_keys(item) for item in data]
    return data


def extract_pdf_if_needed(raw_text: str) -> str:
    """Detect if the text is a latin-1 decoded PDF and extract text via PyPDF.

    This is required when binary PDFs were materialized as latin-1 strings.
    """
    if raw_text.startswith("%PDF-"):
        try:
            raw_bytes = raw_text.encode("latin-1")
            reader = pypdf.PdfReader(io.BytesIO(raw_bytes))

            pages_text = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)

            return "\n".join(pages_text)
        except Exception:
            # If PyPDF fails to extract, fallback to original text.
            pass
    return raw_text

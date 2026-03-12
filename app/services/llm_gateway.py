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


"""LLMGateway — routes extraction requests to Gemini models.

Uses Gemini Flash with response_schema for structured extraction.
Replaces the previous Ollama-based tool calling pipeline.
"""

from __future__ import annotations

from typing import TypeVar

import structlog
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.services.gemini_client import GeminiClient
from app.services.sanitizer import extract_pdf_if_needed

logger = structlog.get_logger()

T = TypeVar("T", bound=BaseModel)

_BUSINESS_RULE_SYSTEM_PROMPT = (
    "You are an expert technical data extractor. "
    "Extract structured information from the provided text. "
    "CRITICAL LANGUAGE RULE: "
    "The input text may be in any language (Portuguese, Spanish, English, etc.). "
    "1. Map extracted concepts to the strict English JSON keys in the schema. "
    "2. Preserve the ORIGINAL LANGUAGE of the input for all JSON values. "
    "DO NOT translate business context or technical terms."
)


class LLMGateway:
    """Extraction gateway using Gemini Flash with response_schema."""

    def __init__(self, client: GeminiClient | None = None) -> None:
        self._client = client or GeminiClient()

    async def extract_business_rules(self, text: str, schema: type[T]) -> T:
        """Extract structured business rules from raw text.

        Uses Gemini Flash with response_schema for reliable structured output.
        Retries up to 3 times on validation failures.
        """
        text = extract_pdf_if_needed(text)

        latest_error: Exception | None = None

        for attempt in range(1, 4):
            try:
                result = await self._client.generate_structured(
                    prompt=text,
                    response_model=schema,
                    model=settings.gemini_flash_model,
                    system_instruction=_BUSINESS_RULE_SYSTEM_PROMPT,
                )
                return result
            except (ValidationError, ValueError) as e:
                latest_error = e
                logger.warning(
                    "business_rule_extraction_failed",
                    attempt=attempt,
                    error=str(e),
                )

        logger.error(
            "business_rule_extraction_exhausted", error=str(latest_error)
        )
        raise latest_error  # type: ignore[misc]

    async def extract_graph_entities(
        self, text: str, schema: type[T], system_prompt: str
    ) -> T:
        """Extract entities and relations for Graph RAG.

        Uses Gemini Flash with response_schema for structured extraction.
        """
        text = extract_pdf_if_needed(text)

        latest_error: Exception | None = None

        for attempt in range(1, 4):
            try:
                result = await self._client.generate_structured(
                    prompt=text,
                    response_model=schema,
                    model=settings.gemini_flash_model,
                    system_instruction=system_prompt,
                )
                return result
            except (ValidationError, ValueError) as e:
                latest_error = e
                logger.warning(
                    "graph_extraction_failed",
                    attempt=attempt,
                    error=str(e),
                )

        logger.error("graph_extraction_exhausted", error=str(latest_error))
        raise latest_error  # type: ignore[misc]

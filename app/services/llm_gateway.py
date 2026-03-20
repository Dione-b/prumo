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


"""LLMGateway — routes requests to local Ollama models for business rule extraction."""

from __future__ import annotations

import json
from typing import Any, TypeVar

import structlog
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.services.ollama_client import OllamaClient

logger = structlog.get_logger()

T = TypeVar("T", bound=BaseModel)

# Limite de caracteres para truncação (aproximadamente 120k tokens)
MAX_CHARS = 480_000


def _sanitize_llm_json(raw: str) -> dict[str, Any]:
    """Extrai JSON de respostas LLM que podem conter markdown fences."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove primeira e última linha (fences)
        json_lines = [line for line in lines[1:] if not line.strip().startswith("```")]
        cleaned = "\n".join(json_lines)
    return json.loads(cleaned)  # type: ignore[no-any-return]


def _pydantic_to_tool(schema: type[BaseModel]) -> dict[str, Any]:
    """Converte um schema Pydantic em tool definition para Ollama."""
    json_schema = schema.model_json_schema()
    return {
        "type": "function",
        "function": {
            "name": schema.__name__,
            "description": json_schema.get("description", "Extract structured data"),
            "parameters": json_schema,
        },
    }


class LLMGateway:
    """Gateway de extração usando OllamaClient."""

    def __init__(self) -> None:
        self.ollama_client = OllamaClient()

    async def extract_business_rules(self, text: str, schema: type[T]) -> T:
        """Gateway para extração de Business Rules via Ollama.

        1. Converte schema em tool definition.
        2. Captura thinking trace para auditoria (C_01).
        3. Parseia resultado de tool_calls[0].function.arguments.
        """
        # Truncação simples por caracteres
        if len(text) > MAX_CHARS:
            text = text[:MAX_CHARS]

        system_prompt = (
            "You are an expert technical data extractor. "
            "Extract structured information from the provided text using the "
            "available tool."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ]

        tools = [_pydantic_to_tool(schema)]

        failures = 0
        latest_error: Exception | None = None

        for attempt in range(1, 4):
            try:
                thinking_models = ["qwen3", "deepseek"]
                model_name = settings.ollama_business_model.lower()
                should_think = any(m in model_name for m in thinking_models)

                response = await self.ollama_client.chat(
                    model=settings.ollama_business_model,
                    messages=messages,
                    tools=tools,
                    think=should_think,
                    options={"num_predict": 2048},
                )

                message = (
                    response.message
                    if hasattr(response, "message")
                    else response.get("message", {})
                )

                # C_01: Capture thinking trace
                thinking_trace = ""
                if hasattr(message, "thinking") and message.thinking:
                    thinking_trace = message.thinking
                    logger.info("ollama_thinking_trace", thinking=thinking_trace)
                elif isinstance(message, dict) and message.get("thinking"):
                    thinking_trace = message["thinking"]
                    logger.info("ollama_thinking_trace", thinking=thinking_trace)

                tool_calls = getattr(
                    message, "tool_calls", message.get("tool_calls", [])
                )

                if tool_calls and len(tool_calls) > 0:
                    tool_call = tool_calls[0]
                    if hasattr(tool_call, "function"):
                        func_obj = tool_call.function
                        arguments = getattr(func_obj, "arguments", {})
                    elif isinstance(tool_call, dict) and "function" in tool_call:
                        arguments = tool_call["function"].get("arguments", {})
                    else:
                        arguments = {}

                    if isinstance(arguments, str):
                        try:
                            parsed_data = json.loads(arguments)
                        except json.JSONDecodeError:
                            parsed_data = _sanitize_llm_json(arguments)
                    else:
                        parsed_data = arguments
                else:
                    content = getattr(message, "content", message.get("content", ""))
                    parsed_data = _sanitize_llm_json(content)

                result = schema(**parsed_data)

                # C_01: Downgrade confidence se thinking indicar contradição
                if thinking_trace and (
                    "contradict" in thinking_trace.lower()
                    or "conflict" in thinking_trace.lower()
                ):
                    if hasattr(result, "confidence_level"):
                        object.__setattr__(result, "confidence_level", "LOW")

                # C_01: Downgrade se muitas falhas de validação
                if failures >= 2 and hasattr(result, "confidence_level"):
                    object.__setattr__(result, "confidence_level", "LOW")

                return result

            except (json.JSONDecodeError, ValidationError) as e:
                failures += 1
                latest_error = e
                logger.warning(
                    "ollama_extraction_failed", attempt=attempt, error=str(e)
                )

        # Fallback após 3 tentativas
        logger.error("ollama_extraction_exhausted", error=str(latest_error))

        default_obj: dict[str, Any] = {}
        for field_name, field_info in schema.model_fields.items():
            if field_name == "confidence_level":
                default_obj[field_name] = "LOW"
            elif field_name == "client_name":
                default_obj[field_name] = "Unknown"
            elif field_name == "core_objective":
                default_obj[field_name] = "Extraction failed due to validation errors"
            elif field_info.annotation is list or str(field_info.annotation).startswith(
                "list"
            ):
                default_obj[field_name] = []
            elif field_info.annotation is str:
                default_obj[field_name] = ""
            else:
                default_obj[field_name] = None

        return schema(**default_obj)

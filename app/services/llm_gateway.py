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


"""LLMGateway — routes requests to local Ollama models."""

from __future__ import annotations

import json
from typing import Any, TypeVar

import structlog
import tiktoken
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.services.ollama_client import OllamaClient
from app.services.sanitizer import (
    extract_pdf_if_needed,
    normalize_keys,
    sanitize_llm_json,
)
from app.utils.tool_converter import pydantic_to_tool

logger = structlog.get_logger()

T = TypeVar("T", bound=BaseModel)


class LLMGateway:
    """Extraction gateway using the sequential OllamaClient."""

    def __init__(self) -> None:
        self.ollama_client = OllamaClient()

    async def extract_business_rules(self, text: str, schema: type[T]) -> T:
        """Thinking-capable gateway for Business Rule extraction.

        1. Convert schema to tool definition.
        2. Capture and log response.message.thinking for auditing (C_01).
        3. Parse result from tool_calls[0].function.arguments.
        """
        text = extract_pdf_if_needed(text)

        # 120k token truncation
        enc = tiktoken.get_encoding("cl100k_base")
        tokens = enc.encode(text)
        max_tokens = 120_000
        if len(tokens) > max_tokens:
            text = enc.decode(tokens[:max_tokens])

        client = self.ollama_client

        system_prompt = (
            "You are an expert technical data extractor. "
            "Extract structured information from the provided text using the "
            "available tool."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ]

        tools = [pydantic_to_tool(schema)]

        failures = 0
        latest_error: Exception | None = None

        for attempt in range(1, 4):
            try:
                thinking_models = ["qwen3", "deepseek"]
                model_name = settings.ollama_business_model.lower()
                should_think = any(m in model_name for m in thinking_models)

                # 2. Call self.ollama_client.chat.
                response = await client.chat(
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

                # C_01: Capture and log thinking trace
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
                            parsed_data = sanitize_llm_json(arguments)
                    else:
                        parsed_data = arguments
                else:
                    content = getattr(message, "content", message.get("content", ""))
                    parsed_data = sanitize_llm_json(content)

                result = schema(**parsed_data)

                # C_01: Audit thinking trace to ensure high-fidelity business rules
                if thinking_trace and (
                    "contradict" in thinking_trace.lower()
                    or "conflict" in thinking_trace.lower()
                ):
                    if hasattr(result, "confidence_level"):
                        object.__setattr__(result, "confidence_level", "LOW")
                        if (
                            hasattr(result, "_warnings")
                            and "contradictory_thinking_downgrade"
                            not in result._warnings
                        ):
                            result._warnings.append(
                                "Confidence downgraded: contradictory thinking trace."
                            )

                # C_01: Enforce confidence downgrades if extraction
                # schema validation fails > 2 times.
                if failures >= 2 and hasattr(result, "confidence_level"):
                    object.__setattr__(result, "confidence_level", "LOW")
                    if (
                        hasattr(result, "_warnings")
                        and "schema_validation_downgrade" not in result._warnings
                    ):
                        result._warnings.append(
                            "Confidence downgraded due to multiple validation failures."
                        )

                return result
            except TimeoutError as e:
                # C_01: Downgrade confidence to MEDIUM if wait exceeds timeout.
                logger.warning("ollama_timeout_downgrade")
                # Fallback dictionary simulating schema extraction loosely
                if (
                    hasattr(schema, "model_fields")
                    and "confidence_level" in schema.model_fields
                ):
                    # Provide default values based on schema structure
                    default_obj_fallback: dict[str, Any] = {}
                    for field_name, field_info in schema.model_fields.items():
                        if field_name == "confidence_level":
                            default_obj_fallback[field_name] = "MEDIUM"
                        elif field_name == "client_name":
                            default_obj_fallback[field_name] = "Unknown"
                        elif field_name == "core_objective":
                            default_obj_fallback[field_name] = (
                                "Extraction timed out due to resource contention"
                            )
                        elif field_info.annotation is list or str(
                            field_info.annotation
                        ).startswith("list"):
                            default_obj_fallback[field_name] = []
                        elif field_info.annotation is str:
                            default_obj_fallback[field_name] = ""
                        else:
                            default_obj_fallback[field_name] = None

                    fallback = schema(**default_obj_fallback)
                    if hasattr(fallback, "_warnings"):
                        fallback._warnings.append(
                            "Semaphore timeout - hardware contention."
                        )
                    return fallback
                raise e  # Throw timeout if confidence downgrade is not supported
            except (json.JSONDecodeError, ValidationError) as e:
                failures += 1
                latest_error = e
                logger.warning(
                    "ollama_extraction_failed", attempt=attempt, error=str(e)
                )

        # If it fails > 2 times, fallback
        logger.error("ollama_extraction_exhausted", error=str(latest_error))

        # Generic fallback
        default_obj: dict[str, Any] = {}
        for field_name, field_info in schema.model_fields.items():
            if field_name == "confidence_level":
                default_obj[field_name] = "LOW"  # C_01 Enforce
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

        fallback = schema(**default_obj)
        if hasattr(fallback, "_warnings"):
            fallback._warnings.append(
                f"Fallback generation after 3 failures: {latest_error}"
            )
        return fallback

    async def extract_graph_entities(
        self, text: str, schema: type[T], system_prompt: str
    ) -> T:
        """Gateway for Graph RAG extraction using agentic models (MiniMax/Soroban)."""
        text = extract_pdf_if_needed(text)

        # 200k token truncation for M2
        enc = tiktoken.get_encoding("cl100k_base")
        tokens = enc.encode(text)
        max_tokens = 200_000
        if len(tokens) > max_tokens:
            text = enc.decode(tokens[:max_tokens])

        client = self.ollama_client

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ]

        tools = [pydantic_to_tool(schema)]

        failures = 0
        latest_error: Exception | None = None

        for attempt in range(1, 4):
            try:
                thinking_models = ["qwen3", "deepseek", "minimax"]
                model_name = settings.ollama_graph_model.lower()
                should_think = any(m in model_name for m in thinking_models)

                response = await client.chat(
                    model=settings.ollama_graph_model,
                    messages=messages,
                    tools=tools,
                    think=should_think,
                    options={"num_predict": 4096},
                )

                message = (
                    response.message
                    if hasattr(response, "message")
                    else response.get("message", {})
                )

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
                            parsed_data = sanitize_llm_json(arguments)
                    else:
                        parsed_data = arguments
                else:
                    content = getattr(message, "content", message.get("content", ""))
                    parsed_data = sanitize_llm_json(content)

                # C_01: Normalize keys to lowercase to handle
                # capitalization inconsistencies from LLMs
                parsed_data = normalize_keys(parsed_data)

                return schema(**parsed_data)
            except TimeoutError as e:
                logger.warning(
                    "ollama_graph_timeout", timeout=settings.ollama_request_timeout
                )
                raise e
            except (json.JSONDecodeError, ValidationError) as e:
                failures += 1
                latest_error = e
                # C_01: Log the raw payload for observability and debugging
                raw_payload = (
                    arguments
                    if "arguments" in locals() and arguments
                    else getattr(message, "content", "")
                )
                logger.warning(
                    "ollama_graph_extraction_failed",
                    attempt=attempt,
                    error=str(e),
                    raw_payload=raw_payload,
                )

        logger.error("ollama_graph_extraction_exhausted", error=str(latest_error))

        default_obj: dict[str, Any] = {}
        for field_name, field_info in schema.model_fields.items():
            if field_info.annotation is list or str(field_info.annotation).startswith(
                "list"
            ):
                default_obj[field_name] = []
            elif field_info.annotation is str:
                default_obj[field_name] = ""
            else:
                default_obj[field_name] = None

        return schema(**default_obj)

"""Pydantic to Ollama Tool schema conversion."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


def pydantic_to_tool(
    model: type[BaseModel],
    name: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Convert a Pydantic model to an Ollama-compatible tool definition.

    Removes the ``$defs`` key that Pydantic v2's ``model_json_schema()``
    emits for nested models — Ollama's tool-calling parser chokes on it.

    Args:
        model: Pydantic BaseModel class to convert.
        name: Override for the tool function name.
        description: Override for the tool function description.

    Returns:
        Ollama-compatible tool dictionary.
    """
    schema = model.model_json_schema()

    # Ollama Native Tool Calling does not accept JSON Schema $defs.
    schema.pop("$defs", None)

    return {
        "type": "function",
        "function": {
            "name": name or schema.get("title", model.__name__),
            "description": description
            or schema.get(
                "description",
                f"Extract structured data matching {model.__name__}",
            ),
            "parameters": {
                "type": "object",
                "properties": schema.get("properties", {}),
                "required": schema.get("required", []),
            },
        },
    }

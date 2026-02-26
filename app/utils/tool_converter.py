"""Pydantic to Ollama Tool schema conversion."""

from typing import Any

from pydantic import BaseModel


def pydantic_to_tool(model: type[BaseModel]) -> dict[str, Any]:
    """Converts Pydantic models to Ollama-compatible function schemas.

    Args:
        model: Pydantic BaseModel class to convert.

    Returns:
        Ollama-compatible tool dictionary.
    """
    schema = model.model_json_schema()
    return {
        "type": "function",
        "function": {
            "name": schema.get("title", model.__name__),
            "description": schema.get(
                "description", f"Extracts data for {model.__name__}"
            ),
            "parameters": {
                "type": "object",
                "properties": schema.get("properties", {}),
                "required": schema.get("required", []),
            },
        },
    }

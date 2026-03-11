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

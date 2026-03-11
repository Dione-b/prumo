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


from __future__ import annotations

from typing import Protocol, TypeVar

T = TypeVar("T")


class CacheProvider(Protocol):
    """
    Zero-cost abstraction for LLM context caching.

    Structural protocol only used at type-check time (no runtime overhead).
    Allows swapping Google GenAI for other providers without touching
    orchestrators or business logic.
    """

    async def count_tokens(self, text: str, model: str) -> int:
        """
        Return the total token count for the given text and model.
        """

    async def create_cached_content(self, content: str, model: str, ttl: int) -> str:
        """
        Create an explicit cached content object and return its cache name.
        """

    async def generate_with_cache(
        self,
        cache_name: str,
        prompt: str,
        schema: type[T],
        model: str = "",
        system_instruction: str | None = None,
    ) -> T:
        """
        Generate a structured response using an existing cached content name.
        """

    async def generate_text(
        self,
        prompt: str,
        system_instruction: str = "",
        model: str = "",
        temperature: float = 0.2,
        cache_name: str | None = None,
    ) -> str:
        """
        Generate free-form text (e.g. YAML) with optional cached context.
        """

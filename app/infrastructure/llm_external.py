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

from app.domain.entities import BusinessRuleExtraction
from app.schemas.business_rule import BusinessRuleSchema
from app.services.llm_gateway import LLMGateway


class ExternalAIEngineAdapter:
    """Infrastructure adapter que esconde providers LLM concretos do core."""

    def __init__(self, gateway: LLMGateway | None = None) -> None:
        self._gateway = gateway or LLMGateway()

    async def extract_business_rules(self, text: str) -> BusinessRuleExtraction:
        result = await self._gateway.extract_business_rules(text, BusinessRuleSchema)
        return BusinessRuleExtraction(
            client_name=result.client_name,
            core_objective=result.core_objective,
            technical_constraints=tuple(result.technical_constraints),
            acceptance_criteria=tuple(result.acceptance_criteria),
            additional_notes=result.additional_notes,
            confidence_level=result.confidence_level,
            warnings=tuple(result.warnings),
        )
